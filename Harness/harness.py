# -*- coding: utf-8 -*-
"""
Harness/harness.py
--------------------
核心調度器（Agent Harness）主流程，對應 Architect/Harness.md 步驟 1–6：

  1-2  輸入前處理（純文字清理）
  3-4  Session 解析、System Prompt 拉取（含 Fallback）
  5-6  上下文綑綁、請求載荷組裝

只負責「組出要送給 LLM 的 payload」，不負責真正呼叫 LLM／工具執行
（那是規格書 6 節「後續串接說明」提到的步驟 7 以後，屬於 LLM/、Tool/、
Guardrails/ 模組的範圍，本次不實作）。

Architect/ThoughtPanelStep.md §6.2：handle_turn() 由「同步回傳
(session_id, payload)」改為 **generator**，即時發射步驟②③④的 StepEvent
（構建請求／拉取當前模式／返回結構化 Prompt），最終以
("result", (session_id, payload)) 收尾。HarnessError（EMPTY_CONTENT／
INVALID_SESSION）語意不變：仍在對應檢查失敗時直接 raise，於呼叫端第一次
迭代（第一個 next()）時就會拋出，不會被誤吞成一個 "step" 事件。
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, Iterator, Optional, Tuple

from Harness.config import DEFAULT_MODE, SLA_PREPROCESS_MS, SLA_REQUEST_BUILD_MS
from Harness.errors import HarnessError, HistoryCorrupted, PromptFetchFailed, empty_content_error
from Harness.payload import assemble_request
from Harness.session import SESSION_STORE
from Harness.text_preprocessing import clean_plain_text
from Prompt.system_prompt_cache import FALLBACK_PROMPT_BLOCK, get_system_prompt
from Trace.step_events import make_step_event

logger = logging.getLogger("harness")

Event = Tuple[str, Any]


def _render_prompt_preview(prompt_block: Dict[str, Any]) -> str:
    """
    步驟④「返回結構化 Prompt」要顯示的內容：依 Architect/ThoughtPanelStep.md
    §8 決定，不遮蔽，原樣呈現角色定義／安全紅線／工具數量，跟
    Harness/payload.py render_system_prompt_content() 實際渲染進 messages
    的內容一致（只是這裡顯示的是「範本」本身，日期佔位符尚未替換——真正
    替換後的完整系統提示詞在後續 assemble_request() 才產生，會完整存在
    request_payload["messages"][0]["content"] 中，供步驟⑤顯示時參考）。
    """
    content = prompt_block.get("content", {})
    metadata = prompt_block.get("metadata", {})
    tool_definitions = content.get("tool_definitions") or []
    return (
        f"template_id={prompt_block.get('template_id')}　version={metadata.get('version')}\n\n"
        f"[角色定義]\n{content.get('role_definition', '')}\n\n"
        f"[安全紅線]\n{content.get('safety_guardrails', '')}\n\n"
        f"[工具定義] {len(tool_definitions)} 項：" + "、".join(t.get("name", "?") for t in tool_definitions)
    )


def handle_turn(
    raw_text: str,
    session_id: Optional[str] = None,
    header_session_id: Optional[str] = None,
    mode: str = DEFAULT_MODE,
    stream: bool = True,
    thinking_mode: bool = True,
) -> Iterator[Event]:
    """
    執行步驟 1–6，即時發射步驟②③④的 StepEvent，最終以
    ("result", (resolved_session_id, request_payload)) 收尾。

    Args:
        raw_text: 使用者原始純文字輸入。
        session_id: 呼叫端已知的 Session ID（例如 Request Body 的 session_id 欄位）。
        header_session_id: 若透過 HTTP 呼叫，優先讀取的 X-Session-Id Header 值。
        mode: 決定使用哪一套系統提示詞。
        stream: 是否以串流方式回應。
        thinking_mode: 是否開啟深度思考模式。

    Yields:
        ("step", StepEvent) — 步驟②③④的即時進度事件。
        ("result", (str, dict)) — 本函式真正的回傳值，generator 收尾前的
            唯一一次 "result" 事件。

    Raises:
        HarnessError: EMPTY_CONTENT（清理後文字為空）或
                      INVALID_SESSION（Session ID 格式錯誤）。這兩種例外都
                      發生在本函式第一個 yield 之前，因此會在呼叫端第一次
                      迭代（第一個 next()）時就直接拋出，語意與改寫前的同步
                      版本一致。
    """
    t0 = time.perf_counter()

    # 步驟 1-2：Session 解析（可能拋出 INVALID_SESSION）。
    resolved_id, session, is_new = SESSION_STORE.resolve(header_session_id, session_id)

    # 步驟 1-2：純文字前處理。
    cleaned_text = clean_plain_text(raw_text)
    t_preprocess_done = time.perf_counter()
    _log_if_over_sla("前處理", t0, t_preprocess_done, SLA_PREPROCESS_MS)

    if not cleaned_text.strip():
        raise empty_content_error()

    # 步驟②：構建請求（攜帶 Session ID）。
    yield "step", make_step_event(
        "build_request",
        status="success",
        delta=(
            f"session_id={resolved_id}（{'新建會話' if is_new else '沿用既有會話'}）\n"
            f"已清理輸入長度：{len(cleaned_text)} 字元"
        ),
        meta={"session_id": resolved_id, "is_new_session": is_new},
    )

    # 步驟③：拉取當前模式（步驟 A：注入系統級指令）。
    yield "step", make_step_event(
        "fetch_prompt_mode", status="running", delta=f"mode={mode}", meta={"mode": mode}
    )
    try:
        prompt_block = get_system_prompt(mode)
        # 步驟④：返回結構化 Prompt。
        yield "step", make_step_event(
            "prompt_ready",
            status="success",
            delta=_render_prompt_preview(prompt_block),
            meta={
                "template_id": prompt_block.get("template_id"),
                "version": prompt_block.get("metadata", {}).get("version"),
            },
        )
    except PromptFetchFailed as exc:
        logger.error("PROMPT_FETCH_FAIL: %s -> fallback to default prompt", exc)
        prompt_block = copy.deepcopy(FALLBACK_PROMPT_BLOCK)
        yield "step", make_step_event(
            "prompt_ready",
            status="error",
            delta=f"System Prompt 拉取失敗：{exc}，已切換備援提示詞。",
            meta={"template_id": prompt_block.get("template_id")},
        )
    session.system_prompt_version = prompt_block.get("metadata", {}).get("version")

    # 步驟 5（步驟 C）：上下文綑綁，取回歷史對話（含毀損重試）。
    try:
        history_messages = session.get_history_messages()
    except HistoryCorrupted as exc:
        logger.error("HISTORY_CORRUPTED: %s -> clearing history for session %s", exc, resolved_id)
        session.history = []
        history_messages = []

    # 步驟 6：組裝最終請求載荷。
    payload = assemble_request(
        session_id=resolved_id,
        prompt_block=prompt_block,
        history_messages=history_messages,
        user_query=cleaned_text,
        stream=stream,
        thinking_mode=thinking_mode,
    )

    # 這一輪的使用者輸入寫回 Session 歷史，供下一輪對話使用。
    session.append_user_message(cleaned_text)
    session.touch()

    t_done = time.perf_counter()
    _log_if_over_sla("請求建構", t0, t_done, SLA_REQUEST_BUILD_MS)

    yield "result", (resolved_id, payload)


def append_assistant_message(session_id: str, content: str) -> None:
    """
    LLM（或目前的假後端）產生完整回覆後呼叫，把回覆寫回該 Session 的歷史，
    讓下一輪對話能延續上下文。
    """
    session = SESSION_STORE.get(session_id)
    if session is None:
        logger.warning("append_assistant_message: unknown session_id=%s", session_id)
        return
    session.append_assistant_message(content)
    session.touch()


def _log_if_over_sla(stage: str, t0: float, t1: float, sla_ms: float) -> None:
    elapsed_ms = (t1 - t0) * 1000
    if elapsed_ms > sla_ms:
        logger.warning("Harness %s 耗時 %.2fms 超過 SLA %.2fms", stage, elapsed_ms, sla_ms)
