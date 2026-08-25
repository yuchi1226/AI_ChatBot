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
"""

from __future__ import annotations

import copy
import logging
import time
from typing import Any, Dict, Optional, Tuple

from Harness.config import DEFAULT_MODE, SLA_PREPROCESS_MS, SLA_REQUEST_BUILD_MS
from Harness.errors import HarnessError, HistoryCorrupted, PromptFetchFailed, empty_content_error
from Harness.payload import assemble_request
from Harness.session import SESSION_STORE
from Harness.text_preprocessing import clean_plain_text
from Prompt.system_prompt_cache import FALLBACK_PROMPT_BLOCK, get_system_prompt

logger = logging.getLogger("harness")


def handle_turn(
    raw_text: str,
    session_id: Optional[str] = None,
    header_session_id: Optional[str] = None,
    mode: str = DEFAULT_MODE,
    stream: bool = True,
    thinking_mode: bool = True,
) -> Tuple[str, Dict[str, Any]]:
    """
    執行步驟 1–6，回傳 (resolved_session_id, request_payload)。

    Args:
        raw_text: 使用者原始純文字輸入。
        session_id: 呼叫端已知的 Session ID（例如 Request Body 的 session_id 欄位）。
        header_session_id: 若透過 HTTP 呼叫，優先讀取的 X-Session-Id Header 值。
        mode: 決定使用哪一套系統提示詞。
        stream: 是否以串流方式回應。
        thinking_mode: 是否開啟深度思考模式。

    Raises:
        HarnessError: EMPTY_CONTENT（清理後文字為空）或
                      INVALID_SESSION（Session ID 格式錯誤）。
    """
    t0 = time.perf_counter()

    # 步驟 1-2：Session 解析（可能拋出 INVALID_SESSION）。
    resolved_id, session, _is_new = SESSION_STORE.resolve(header_session_id, session_id)

    # 步驟 1-2：純文字前處理。
    cleaned_text = clean_plain_text(raw_text)
    t_preprocess_done = time.perf_counter()
    _log_if_over_sla("前處理", t0, t_preprocess_done, SLA_PREPROCESS_MS)

    if not cleaned_text.strip():
        raise empty_content_error()

    # 步驟 3（步驟 A）：注入系統級指令，拉取 System Prompt（含 Fallback）。
    try:
        prompt_block = get_system_prompt(mode)
    except PromptFetchFailed as exc:
        logger.error("PROMPT_FETCH_FAIL: %s -> fallback to default prompt", exc)
        prompt_block = copy.deepcopy(FALLBACK_PROMPT_BLOCK)
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

    return resolved_id, payload


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
