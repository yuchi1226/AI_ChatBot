# -*- coding: utf-8 -*-
"""
LLMReasoning/reasoning.py
----------------------------
核心協調流程，對應 Architect/LLMReasoning.md §3.1–3.3、§4，並整合
Architect/ToolCalling.md §5、§6：

  3.1 組裝完整 Prompt      -> 已由 Harness.handle_turn() 完成，本模組直接
                              收現成的 request_payload，不重複組裝。
  3.2 呼叫 LLM＋深度思考    -> 委派給 LLM.stream_answer()，逐一轉發串流事件
                              給呼叫端（目前是 Frontend），同時在旁累積
                              reason_content／content／tool_calls。
  3.3 判斷是否呼叫工具      -> decide_action()（見 actions.py）。
  §4 後續流轉：
    無需呼叫工具 -> content 即最終回覆，寫回 Session 歷史，結束。
    需要呼叫工具 -> 依序做兩層檢查：
      ① §5 結構檢查（LLMReasoning.actions.validate_tool_calls）：這段 JSON
        本身合不合法（function.name 是否存在、arguments 是否為合法 JSON）。
        不合法 -> 模型連格式都吐不出來，重試也修不好，立即回錯誤提示。
      ② ToolCalling.md §6 白名單/型態檢查（Tool.validate_against_catalog）：
        名稱在不在 Tool/catalog.py 的白名單內、必填參數齊不齊全、型態對不
        對。不合法 -> 觸發 §6 規定的重試機制：在 messages 尾端附加修正提示，
        要求模型重新生成 tool_calls，最多 Tool.RETRY_MAX（2）次；重試次數
        用盡仍不合法，才回錯誤提示。
    兩層檢查都通過後，把 reason_content／tool_calls 暫存進 Session，經過
    Guardrails.precheck()（步驟⑨）後逐一交付工具執行管道（Backend.execute_tool()，
    對應 Architect.md 循序圖步驟⑧–⑬）執行，取得 tool_results 後立即流轉進
    resume_with_tool_result() 做 Architect/AgentLoop.md §3.1–3.4 的第二輪推理
    （步驟⑭–⑰）。

Architect/ThoughtPanelStep.md §6.3、§6.6：process()／resume_with_tool_result()
的事件全面改用統一的 ("step", Trace.StepEvent) 事件，取代舊版
("thought_chunk"/"response_chunk"/"metadata", ...) 事件——步驟⑤⑥⑦A/⑦B、
⑧A/⑧B、⑨、⑭⑮⑯⑰ 皆即時發射；confidence_score／cited_sources／
reasoning_summary 併入步驟⑰的 StepEvent.meta，不再用獨立的 "metadata" 事件。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

import Backend
import Guardrails
import Harness
import LLM
import Tool
from Harness.text_preprocessing import approx_token_count
from LLMReasoning.actions import Action, decide_action, validate_tool_calls
from LLMReasoning.agent_loop import (
    SecondRoundResult,
    build_final_prompt,
    build_reasoning_summary,
    cited_sources,
    compute_confidence_score,
    detect_conflicts,
    format_tool_results,
    is_stale,
    needs_disclaimer,
    reassemble_context,
)
from LLMReasoning.config import (
    AGENT_LOOP_E2E_LATENCY_WARN_SECONDS,
    MAX_REASONING_TOKENS,
    REASONING_TOKEN_WARN_RATIO,
)
from LLMReasoning.errors import ToolCallFormatError
from Trace.step_events import make_step_event

logger = logging.getLogger("llm_reasoning")
_audit_logger = logging.getLogger("audit.agent_loop")

Event = Tuple[str, Optional[Any]]


def _log_reasoning_token_usage(reason_content: str) -> None:
    """
    §6 效能指標「推理草稿 token 使用率 ≤ 80% 的 max_reasoning_tokens」／
    §5「推理內容截斷（reason_content 被截斷）」的警告來源：沿用
    Harness/text_preprocessing.py 同一套粗略字元權重估算（專案目前沒有
    正式 tokenizer），超過門檻就記警告，不中斷流程、仍使用現有推理草稿
    繼續往下走。
    """
    if not reason_content:
        return
    used = approx_token_count(reason_content)
    if MAX_REASONING_TOKENS <= 0:
        return
    ratio = used / MAX_REASONING_TOKENS
    if ratio >= REASONING_TOKEN_WARN_RATIO:
        logger.warning(
            "推理草稿 token 使用率約 %.0f%%（約 %.0f / %d），可能已被截斷，"
            "仍延用現有推理草稿繼續流程。",
            ratio * 100,
            used,
            MAX_REASONING_TOKENS,
        )


def _build_tool_execution_request(call: Dict[str, Any], index: int) -> Backend.ToolExecutionRequest:
    """
    把 LLM 吐出的 tool_call（已通過 §5 結構檢查 validate_tool_calls() 與
    ToolCalling.md §6 白名單驗證 Tool.validate_against_catalog()）轉成
    Backend.ToolExecutionRequest，交付工具執行管道。

    arguments 已經過 validate_tool_calls() 檢查，若是字串一定能被解析成
    合法 JSON，這裡不需要再包一層 try/except。tool_call_id 優先採用模型
    給的 "id"；Ollama 的 tool_calls 不一定會帶 id，缺漏時退回
    "call_{index}"（用呼叫順序而非工具名稱當備援，避免同一輪呼叫兩次同一
    個工具時互相覆蓋）。
    """
    function = call.get("function", {})
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    return Backend.ToolExecutionRequest(
        tool_call_id=call.get("id") or f"call_{index}",
        tool_name=function.get("name", ""),
        arguments=arguments,
    )


def _extract_user_query(messages: List[Dict[str, Any]]) -> str:
    """
    從 messages（system + history + user，見 Harness/payload.py
    assemble_request()）取回最後一則 role="user" 訊息，供 process() 在
    重試迴圈開始「之前」擷取這一輪的原始使用者提問使用（見 process() 開頭
    的 user_query 擷取）。

    刻意不在 resume_with_tool_result() 內部才呼叫這個函式：ToolCalling.md
    §6 重試機制會在 messages 尾端附加修正提示（同樣是 role="user"，見
    _append_retry_notice()），若重試發生過，屆時 request_payload 裡「最後
    一則 user 訊息」會變成那則修正提示，而不是使用者真正問的問題——所以
    必須由 process() 在任何重試發生之前，先擷取一次「乾淨」的原始提問，
    再明確傳給 resume_with_tool_result()，供 §3.1 reassemble_context() 的
    「用戶提問」分區使用。
    """
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content", "")
    return ""


def _stash_pending_reasoning(
    session_id: str, reason_content: str, tool_calls: List[Dict[str, Any]]
) -> None:
    """§4「需呼叫工具」分支②：把本輪 reason_content 及原始 tool_calls 暫存於會話上下文。"""
    session = Harness.SESSION_STORE.get(session_id)
    if session is None:
        logger.warning("_stash_pending_reasoning: unknown session_id=%s", session_id)
        return
    session.pending_reason_content = reason_content or None
    session.pending_tool_calls = tool_calls
    session.touch()


def _clear_pending_reasoning(session_id: str) -> None:
    """本輪已經以降級文字結束、不會再有 resume_with_tool_result() 接手時，清空暫存狀態。"""
    session = Harness.SESSION_STORE.get(session_id)
    if session is None:
        return
    session.pending_reason_content = None
    session.pending_tool_calls = None
    session.touch()


def _append_retry_notice(request_payload: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
    """
    ToolCalling.md §6：重試前，在 messages 尾端附加一則修正提示，告訴模型
    上一次的 tool_calls 哪裡不合法，要求重新生成。

    只回傳一份新的 request_payload（複製一份新的 messages 陣列），不修改
    呼叫端傳入的原始物件，也不寫回 Session 歷史——重試是這一輪同步發生的
    事，不需要留存到下一輪對話裡。
    """
    messages = list(request_payload.get("messages", []))
    messages.append(
        {
            "role": "user",
            "content": (
                f"你上一次產生的工具呼叫不合法：{exc}。"
                "請重新產生正確的 tool_calls（工具名稱需在系統提示詞的工具清單內，"
                "且包含所有必填參數）。"
            ),
        }
    )
    return {**request_payload, "messages": messages}


def process(session_id: str, request_payload: Dict[str, Any]) -> Iterator[Event]:
    """
    對應 §3.2–3.3 + §4，並整合 ToolCalling.md §6 的重試機制：呼叫 LLM、判定
    動作、視需要重試、流轉到對應分支。

    Args:
        session_id: Harness.handle_turn() 回傳的（已解析）Session ID。
        request_payload: Harness.handle_turn() 回傳的完整請求載荷。

    Yields:
        ("step", Trace.StepEvent) — 步驟⑤⑥⑦⑧⑨…的即時進度事件，供呼叫端
            （Frontend）直接轉發顯示；step_key 在 Trace.MIRRORS_TO_CHAT 內時，
            其 delta 也要同步進左側聊天氣泡（見 Frontend/app.py）。
        ("end", None) — 本輪對話結束。

        （重試期間每一次嘗試的串流事件一樣即時轉發，讓使用者看得到模型仍在
        運作，不會整段卡住無回應。若最終判定需要呼叫工具，本函式會把事件流
        交給 resume_with_tool_result()（Architect/AgentLoop.md §3.1–3.4 第二輪
        推理，步驟⑭–⑰），該函式在 "end" 之前還會多送一個步驟⑰的 StepEvent，
        其 meta 帶有 confidence_score／cited_sources／reasoning_summary，
        供前端「信心分數 < 0.6 顯示免責聲明」的 UI 使用。）
    """
    max_attempts = Tool.RETRY_MAX + 1  # §6：最多重試 2 次 = 最多嘗試 3 次。
    # 在重試迴圈開始「之前」擷取一次原始使用者提問：重試會在 messages 尾端
    # 附加修正提示（見 _append_retry_notice()），若之後才擷取會抓到修正
    # 提示而非使用者真正的問題（見 _extract_user_query() 文件字串）。
    user_query = _extract_user_query(request_payload.get("messages", []))
    reason_content = ""
    content = ""
    tool_calls: List[Dict[str, Any]] = []
    catalog_error: Optional[Tool.ToolError] = None

    # 步驟⑤：發送完整 Prompt＋歷史對話＋提問（重試沿用同一次，不重複發射）。
    yield "step", make_step_event(
        "send_to_llm_r1",
        status="success",
        delta=(
            f"歷史 {max(len(request_payload.get('messages', [])) - 2, 0)} 則訊息，"
            f"thinking_mode={request_payload.get('thinking_mode')}，"
            f"tools={len(request_payload.get('tools') or [])} 項"
        ),
    )

    for attempt in range(max_attempts):
        if attempt > 0:
            yield "step", make_step_event(
                "llm_tool_calls",
                status="running",
                delta=f"\n\n— 第 {attempt + 1}/{max_attempts} 次嘗試重新產生 tool_calls —\n",
                meta={"retry_count": attempt},
            )

        thinking_parts: List[str] = []
        response_parts: List[str] = []
        tool_calls = []
        thinking_open = False
        response_open = False

        for event, data in LLM.stream_answer(request_payload):
            if event == "thought_chunk":
                thinking_parts.append(data or "")
                if data:
                    # 步驟⑥：深度思考（Thinking Mode），逐 token 真即時串流。
                    yield "step", make_step_event("llm_thinking_r1", status="running", delta=data)
                    thinking_open = True
            elif event == "response_chunk":
                response_parts.append(data or "")
                if data:
                    # 步驟⑦A（暫定）：直接返回最終回答，逐 token 真即時串流；
                    # 若稍後判定為 TOOL_CALL，這段文字會被收尾標記為
                    # skipped（見下方），因為它其實是工具呼叫前的暫存提示語
                    # （LLMReasoning.md §3.3），不是最終回覆。
                    yield "step", make_step_event(
                        "llm_final_answer_direct", status="running", delta=data, branch="final_direct"
                    )
                    response_open = True
            elif event == "tool_calls":
                tool_calls = data or []
            elif event == "end":
                break

        reason_content = "".join(thinking_parts)
        content = "".join(response_parts)
        if thinking_open:
            yield "step", make_step_event("llm_thinking_r1", status="success", delta="")
        _log_reasoning_token_usage(reason_content)

        action = decide_action(tool_calls)

        if action is Action.FINAL_ANSWER:
            # §4「無需呼叫工具」分支①②③：content 即最終回覆，寫回歷史，
            # 由呼叫端（Harness）透過 Frontend 回傳給使用者。重試迴圈中途
            # 模型改變主意、不再需要工具了，一樣視為正常結束，不算重試失敗。
            yield "step", make_step_event(
                "llm_final_answer_direct",
                status="success",
                delta="" if response_open else content,
                branch="final_direct",
            )
            Harness.append_assistant_message(session_id, content)
            # 步驟⑧A：輸出最終回覆（短路徑到此結束）。
            yield "step", make_step_event(
                "deliver_final_answer", status="success", delta="已完成，回覆已送出。"
            )
            yield "end", None
            return

        # Action.TOOL_CALL：先收尾步驟⑦A的暫存提示語（若有），再開步驟⑦B。
        if response_open:
            yield "step", make_step_event(
                "llm_final_answer_direct",
                status="skipped",
                delta="",
                branch="final_direct",
                meta={"note": "此段文字為工具呼叫前的暫存提示語，最終回覆將由第二輪推理重新生成。"},
            )

        # 步驟⑦B：返回工具調用指令。依 §8 不遮蔽，完整顯示 tool_calls JSON。
        yield "step", make_step_event(
            "llm_tool_calls",
            status="success",
            delta=json.dumps(tool_calls, ensure_ascii=False, indent=2),
            branch="tool_call",
        )

        # 先做 §5 結構檢查，此檢查失敗代表模型連 JSON 都吐不出來，不屬於
        # ToolCalling.md §6「白名單/型態錯誤」的重試範圍，不重試，直接回
        # 錯誤提示。
        try:
            validate_tool_calls(tool_calls)
        except ToolCallFormatError as exc:
            logger.error("ToolCallFormatError: %s", exc)
            error_notice = "⚠️ 工具呼叫指令格式有誤，暫時無法處理，請重新描述您的問題。"
            Harness.append_assistant_message(session_id, error_notice)
            yield "step", make_step_event("llm_tool_calls", status="error", delta=f"\n{exc}")
            yield "step", make_step_event(
                "llm_final_answer_direct", status="error", delta=error_notice, branch="final_direct"
            )
            yield "end", None
            return

        # ToolCalling.md §6：白名單/必填參數/型態檢查。
        try:
            Tool.validate_against_catalog(tool_calls)
            catalog_error = None
            break  # 通過驗證，跳出重試迴圈，往下走「暫存 + 交付工具管道」。
        except Tool.ToolError as exc:
            catalog_error = exc
            if attempt >= max_attempts - 1:
                break  # §6：重試次數用盡，往下走「回傳錯誤提示」。
            logger.warning(
                "Tool 白名單/型態驗證失敗（第 %d/%d 次嘗試）：%s，要求模型重新生成 tool_calls",
                attempt + 1,
                max_attempts,
                exc,
            )
            yield "step", make_step_event(
                "llm_tool_calls",
                status="error",
                delta=f"\n驗證失敗：{exc}\n將要求模型重新生成 tool_calls…",
                meta={"retry_count": attempt},
            )
            request_payload = _append_retry_notice(request_payload, exc)
            continue

    if catalog_error is not None:
        # §6：重試 Tool.RETRY_MAX 次仍失敗 -> 不執行工具，立即回傳錯誤提示，
        # 要求使用者重新提問（比照 §5 格式錯誤的既有降級文案風格）。
        logger.error(
            "工具呼叫白名單/型態驗證重試 %d 次後仍失敗：%s", Tool.RETRY_MAX, catalog_error
        )
        error_notice = "⚠️ 工具呼叫指令內容有誤，暫時無法處理，請重新描述您的問題。"
        Harness.append_assistant_message(session_id, error_notice)
        yield "step", make_step_event(
            "llm_tool_calls",
            status="error",
            delta=f"\n重試 {Tool.RETRY_MAX} 次後仍失敗：{catalog_error}",
        )
        yield "step", make_step_event(
            "llm_final_answer_direct", status="error", delta=error_notice, branch="final_direct"
        )
        yield "end", None
        return

    # §4「需呼叫工具」分支①②：驗證通過，暫存推理草稿與工具呼叫，供
    # resume_with_tool_result() 做第二輪推理時讀取 original_draft。
    _stash_pending_reasoning(session_id, reason_content, tool_calls)

    # 步驟⑧B：交付工具調用請求。
    tool_names = [c.get("function", {}).get("name", "?") for c in tool_calls]
    yield "step", make_step_event(
        "dispatch_tool_pipeline",
        status="success",
        delta=f"交付 {len(tool_calls)} 個工具呼叫：{'、'.join(tool_names)}",
        meta={"tool_names": tool_names},
    )

    # 步驟⑨：Guardrails 前置鉤子（權限/敏感詞審查）。逐一審查每個
    # tool_call：先跑規則式檢查，放行的才進 LLM 二次複核（見
    # Guardrails/precheck.py）。攔截粒度是單一 tool_call，被擋下的在下面
    # ⑩～⑬迴圈中直接合成拒絕結果，不呼叫 Backend.execute_tool，其餘沒被
    # 擋下的工具呼叫照常執行。
    guardrails_blocked: Dict[int, Guardrails.RejectionReason] = {}
    for event, data in Guardrails.precheck(tool_calls, reason_content):
        if event == "step":
            yield "step", data
        elif event == "result":
            guardrails_blocked = data["blocked"]

    # 步驟⑩～⑬：逐一交付工具執行管道（Backend.execute_tool()，真即時串流，
    # 見 Backend/pipeline.py）。
    tool_results: List[Backend.FinalToolResult] = []
    for index, call in enumerate(tool_calls):
        request = _build_tool_execution_request(call, index)

        if index in guardrails_blocked:
            # 步驟⑨攔截：比照下方 PermissionError 分支的處理方式——合成一筆
            # 失敗的 FinalToolResult，補發⑩～⑬的錯誤狀態事件（顯示原則 5：
            # 錯誤也要走完整四格顯示），不呼叫 Backend.execute_tool，讓第二輪
            # 推理仍有機會誠實告知使用者這部分被拒絕，而不是整輪對話無聲
            # 失敗，也不會因為一個工具被擋就連帶中止其餘工具呼叫。
            rejection = guardrails_blocked[index]
            logger.warning(
                "工具「%s」遭 Guardrails 步驟⑨攔截：%s", request.tool_name, rejection.internal_detail
            )
            for step_key in ("tool_execute", "tool_raw_result", "tool_post_process", "tool_result_ready"):
                yield "step", make_step_event(
                    step_key,
                    status="error",
                    delta=rejection.public_message,
                    meta={
                        "tool_call_id": request.tool_call_id,
                        "error_code": "GUARDRAILS_BLOCKED",
                        "category": rejection.category,
                    },
                )
            tool_results.append(
                Backend.FinalToolResult(
                    tool_call_id=request.tool_call_id,
                    is_success=False,
                    content=rejection.public_message,
                    metadata={"error_code": "GUARDRAILS_BLOCKED", "category": rejection.category},
                )
            )
            continue

        try:
            final_result: Optional[Backend.FinalToolResult] = None
            for event, data in Backend.execute_tool(request):
                if event == "step":
                    yield "step", data
                elif event == "result":
                    final_result = data
            if final_result is not None:
                tool_results.append(final_result)
        except PermissionError as exc:
            # Backend/pipeline.py 對本地執行權限不足刻意不攔截、原樣往外拋，
            # 讓呼叫端能區分「工具本身執行失敗」與「需要重新授權才能繼續」
            # （見 Backend.execute_tool() 文件字串）。Guardrails/ 的使用者
            # 授權流程尚未實作，這裡先把它也當成一次失敗的工具結果處理，
            # 而不是讓整個請求中斷——讓第二輪推理仍有機會誠實告知使用者
            # 「這部分資訊無法取得」，而不是整輪對話無聲失敗。補發步驟⑩～⑬
            # 的錯誤狀態事件，確保錯誤也走完整的四格顯示（顯示原則 5）。
            logger.warning("工具「%s」執行遭拒（PermissionError）：%s", request.tool_name, exc)
            denial_message = f"抱歉，執行「{request.tool_name}」需要額外授權，暫時無法提供此部分資訊。"
            for step_key in ("tool_execute", "tool_raw_result", "tool_post_process", "tool_result_ready"):
                yield "step", make_step_event(
                    step_key,
                    status="error",
                    delta=denial_message,
                    meta={"tool_call_id": request.tool_call_id, "error_code": "PERMISSION_DENIED"},
                )
            tool_results.append(
                Backend.FinalToolResult(
                    tool_call_id=request.tool_call_id,
                    is_success=False,
                    content=denial_message,
                    metadata={"error_code": "PERMISSION_DENIED"},
                )
            )

    # §4「需呼叫工具」分支③／Architect/AgentLoop.md 步驟⑭–⑰：工具結果到手，
    # 立即流轉進第二輪推理。resume_with_tool_result() 會負責把最終回覆寫回
    # Session 歷史並清空 pending 狀態，這裡不重複做。user_query 用的是重試
    # 迴圈開始「之前」擷取的原始提問（見函式開頭），不受重試附加訊息影響。
    yield from resume_with_tool_result(session_id, request_payload, tool_results, user_query)


def resume_with_tool_result(
    session_id: str,
    request_payload: Dict[str, Any],
    tool_results: List[Backend.FinalToolResult],
    user_query: str = "",
) -> Iterator[Event]:
    """
    對應 Architect/Architect.md 循序圖步驟 ⑭–⑰／Architect/AgentLoop.md
    §3.1–3.4：工具執行管道（Backend.execute_tool()）完成、拿到結果後，
    結合本輪暫存的 pending_reason_content（即規格書所說的 original_draft）
    與 tool_results 做第二輪推理，產生最終自然語言回覆，並計算 §4 輸出
    規格所需的中繼資料（confidence_score／cited_sources／reasoning_summary）。

    四個子步驟（§3.1–3.4 上下文重組、資料清理與特徵萃取、邏輯校準、NLG
    編排）委派給 LLMReasoning/agent_loop.py 的純函式；本函式只負責跟
    process() 一樣的「呼叫 LLM、累積串流片段」骨架，以及寫回 Session、
    清空 pending 狀態這些有副作用的收尾動作，並即時發射步驟⑭⑮⑯⑰的
    StepEvent。

    Args:
        session_id: 本輪對話的 Session ID，需帶有 process() 暫存的
            pending_reason_content／pending_tool_calls（透過
            Harness.SESSION_STORE.get(session_id) 取得）。
        request_payload: 本輪第一次呼叫 LLM 時用的完整請求載荷（Harness
            組好的 messages/tools/thinking_mode/...）。第二輪在其 messages
            尾端追加一則 §3.1 組好的增強脈絡訊息後重新送出，沿用同一份
            系統提示詞與歷史對話，不重新呼叫 Harness／Prompt 拉取。
        tool_results: 工具執行管道（Backend.execute_tool()）回傳的結果列表。
        user_query: 這一輪的原始使用者提問，供 §3.1 reassemble_context()
            的「用戶提問」分區使用。process() 一律會傳入（在其重試迴圈
            開始之前擷取的乾淨提問，見 process() 開頭）；未傳入時（例如
            未來獨立呼叫此函式）退回從 request_payload["messages"] 擷取
            最後一則 role="user" 訊息，可能包含重試修正提示。

    Yields:
        ("step", Trace.StepEvent) — 步驟⑭⑮⑯⑰的即時進度事件；步驟⑰的
            StepEvent.meta 帶有 confidence_score／cited_sources／
            reasoning_summary／needs_disclaimer（取代舊版獨立的 "metadata"
            事件）。
        ("end", None) — 本輪對話結束。
    """
    t0 = time.perf_counter()

    session = Harness.SESSION_STORE.get(session_id)
    original_draft = (session.pending_reason_content if session else None) or ""

    # §3.1–3.2：組「增強脈絡」+ 矛盾標記；§5：token 溢出時的壓縮摘要子程序
    # 內嵌在 format_tool_results() 裡。
    if not user_query:
        user_query = _extract_user_query(request_payload.get("messages", []))
    tool_results_text = format_tool_results(tool_results)
    conflict_note = detect_conflicts(tool_results)
    stale = is_stale(tool_results)
    enhanced_context = reassemble_context(user_query, original_draft, tool_results_text)

    # §3.3：組最終提示詞（§3.4 的 NLG 措辭要求已寫在指令文字中），當作新的
    # 一則 user 訊息接在原本對話後面，做第二次 forward pass。
    final_prompt_text = build_final_prompt(enhanced_context, conflict_note, stale)
    second_round_payload = {
        **request_payload,
        "messages": [*request_payload.get("messages", []), {"role": "user", "content": final_prompt_text}],
    }

    # 步驟⑭：工具結果＋原始思考草稿再次送入模型。
    yield "step", make_step_event(
        "send_to_llm_r2",
        status="success",
        delta=enhanced_context,
        meta={"conflict": bool(conflict_note), "stale": stale},
    )

    response_parts: List[str] = []
    thinking_open = False
    for event, data in LLM.stream_answer(second_round_payload):
        if event == "thought_chunk":
            if data:
                # 步驟⑮：綜合分析工具返回的信息，逐 token 真即時串流。
                yield "step", make_step_event("llm_thinking_r2", status="running", delta=data)
                thinking_open = True
        elif event == "response_chunk":
            response_parts.append(data or "")
            if data:
                # 步驟⑯：生成最終自然語言回覆，逐 token 真即時串流。
                yield "step", make_step_event("llm_final_answer_r2", status="running", delta=data)
        elif event == "tool_calls":
            # AgentLoop 是工具呼叫後的「最終」綜合階段，規格未定義在此
            # 遞迴再次呼叫工具；記錄下來但不處理，避免無限流轉。
            logger.warning("第二輪推理中模型再次要求呼叫工具，AgentLoop 階段不處理，忽略：%s", data)
        elif event == "end":
            break

    if thinking_open:
        yield "step", make_step_event("llm_thinking_r2", status="success", delta="")

    final_answer = "".join(response_parts)
    if not final_answer:
        # §5「工具結果為空」／模型第二輪仍未產出任何內容：輸出引導性回覆，
        # 不得隨意捏造數據。
        final_answer = "目前查詢到的資料不足以完整回答這個問題，建議調整篩選條件或補充更多細節後再試一次。"
        yield "step", make_step_event("llm_final_answer_r2", status="success", delta=final_answer)
    else:
        yield "step", make_step_event("llm_final_answer_r2", status="success", delta="")

    # §4 輸出規格：confidence_score／cited_sources／reasoning_summary。
    confidence_score = compute_confidence_score(tool_results, conflict_note)
    result = SecondRoundResult(
        final_answer=final_answer,
        confidence_score=confidence_score,
        cited_sources=cited_sources(tool_results),
        reasoning_summary=build_reasoning_summary(tool_results, conflict_note, stale),
    )

    elapsed_seconds = time.perf_counter() - t0
    if elapsed_seconds > AGENT_LOOP_E2E_LATENCY_WARN_SECONDS:
        logger.warning(
            "Agent Loop 第二輪推理耗時 %.2fs，超過 §6 SLA %.1fs",
            elapsed_seconds,
            AGENT_LOOP_E2E_LATENCY_WARN_SECONDS,
        )
    _audit_logger.info(
        "second_round_result session_id=%s confidence_score=%.2f cited_sources=%s reasoning_summary=%s",
        session_id,
        result.confidence_score,
        result.cited_sources,
        result.reasoning_summary,
    )

    Harness.append_assistant_message(session_id, final_answer)
    _clear_pending_reasoning(session_id)

    # 步驟⑰：輸出最終答案（結束）。confidence_score／cited_sources／
    # reasoning_summary 併入本步驟的 meta，取代舊版獨立的 "metadata" 事件。
    yield "step", make_step_event(
        "deliver_final_answer_r2",
        status="success",
        delta="已完成，回覆已送出。",
        meta={
            "confidence_score": result.confidence_score,
            "cited_sources": result.cited_sources,
            "reasoning_summary": result.reasoning_summary,
            "needs_disclaimer": needs_disclaimer(result.confidence_score),
        },
    )
    yield "end", None


__all__ = ["process", "resume_with_tool_result"]
