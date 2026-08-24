# -*- coding: utf-8 -*-
"""
LLMReasoning/reasoning.py
----------------------------
核心協調流程，對應 Architect/LLMReasoning.md §3.1–3.3、§4：

  3.1 組裝完整 Prompt      -> 已由 Harness.handle_turn() 完成，本模組直接
                              收現成的 request_payload，不重複組裝。
  3.2 呼叫 LLM＋深度思考    -> 委派給 LLM.stream_answer()，逐一轉發串流事件
                              給呼叫端（目前是 Frontend），同時在旁累積
                              reason_content／content／tool_calls。
  3.3 判斷是否呼叫工具      -> decide_action()（見 actions.py）。
  §4 後續流轉：
    無需呼叫工具 -> content 即最終回覆，寫回 Session 歷史，結束。
    需要呼叫工具 -> 先驗證 tool_calls 格式（§5 格式錯誤 -> 立即回錯誤提示，
                    不進入暫存流程）；格式合法則把 reason_content／
                    tool_calls 暫存進 Session（供 Tool/、Guardrails/ 套件
                    完工後，由 resume_with_tool_result() 接手做第二輪
                    推理）。因為 Tool/、Guardrails/ 目前尚未實作，本輪
                    立即以降級文字答覆，並清空暫存狀態（這一輪不會再有人
                    來 resume 它）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

import Harness
import LLM
from Harness.text_preprocessing import approx_token_count
from LLMReasoning.actions import Action, decide_action, validate_tool_calls
from LLMReasoning.config import MAX_REASONING_TOKENS, REASONING_TOKEN_WARN_RATIO
from LLMReasoning.errors import ToolCallFormatError

logger = logging.getLogger("llm_reasoning")

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


def _tool_pipeline_unavailable_notice(tool_calls: List[Dict[str, Any]]) -> str:
    """
    Tool/、Guardrails/ 套件尚未實作時的降級行為：模型想呼叫工具，但目前沒有
    工具執行管線可以接手處理，於是記錄警告並回傳一段對使用者誠實的說明
    文字，而不是靜默吞掉、留一顆永遠空白的回覆泡泡給使用者。

    （這段邏輯原本在 LLM/llm.py；搬來這裡是因為「要不要呼叫工具管線」屬於
    決策，不屬於「跟模型溝通」——見 LLM/ 與 LLMReasoning/ 的職責劃分。）
    """
    names = ", ".join(
        call.get("function", {}).get("name", "unknown") for call in tool_calls
    ) or "unknown"
    logger.warning(
        "模型要求呼叫工具（%s），但 Tool/Guardrails 管線尚未實作，略過執行。", names
    )
    return f"（這個問題可能需要使用工具「{names}」協助回答，但工具執行功能尚未上線，暫時無法提供。）"


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


def process(session_id: str, request_payload: Dict[str, Any]) -> Iterator[Event]:
    """
    對應 §3.2–3.3 + §4：呼叫 LLM、判定動作、流轉到對應分支。

    Args:
        session_id: Harness.handle_turn() 回傳的（已解析）Session ID。
        request_payload: Harness.handle_turn() 回傳的完整請求載荷。

    Yields:
        跟 LLM.stream_answer() 相同的事件格式，供呼叫端（Frontend）直接
        轉發顯示：
            ("thought_chunk",  <思考內容片段>)
            ("response_chunk", <最終回覆片段>)
            ("end",             None)
        （LLM.stream_answer() 額外送出的 "tool_calls" 事件會在這裡被消化，
        不會轉發給呼叫端。）
    """
    thinking_parts: List[str] = []
    response_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []

    for event, data in LLM.stream_answer(request_payload):
        if event == "thought_chunk":
            thinking_parts.append(data or "")
            yield event, data
        elif event == "response_chunk":
            response_parts.append(data or "")
            yield event, data
        elif event == "tool_calls":
            tool_calls = data or []
        elif event == "end":
            break

    reason_content = "".join(thinking_parts)
    content = "".join(response_parts)
    _log_reasoning_token_usage(reason_content)

    action = decide_action(tool_calls)

    if action is Action.FINAL_ANSWER:
        # §4「無需呼叫工具」分支①②③：content 即最終回覆，寫回歷史，
        # 由呼叫端（Harness）透過 Frontend 回傳給使用者。
        Harness.append_assistant_message(session_id, content)
        yield ("end", None)
        return

    # Action.TOOL_CALL
    try:
        validate_tool_calls(tool_calls)
    except ToolCallFormatError as exc:
        # §5：工具呼叫格式錯誤 -> 不執行工具，立即回傳錯誤提示，要求重新提問。
        logger.error("ToolCallFormatError: %s", exc)
        error_notice = "⚠️ 工具呼叫指令格式有誤，暫時無法處理，請重新描述您的問題。"
        Harness.append_assistant_message(session_id, error_notice)
        yield ("response_chunk", error_notice)
        yield ("end", None)
        return

    # §4「需呼叫工具」分支①②：暫存推理草稿與工具呼叫，供未來 Tool/Guardrails
    # 管線接上後由 resume_with_tool_result() 做第二輪推理。
    _stash_pending_reasoning(session_id, reason_content, tool_calls)

    # Tool/、Guardrails/ 尚未實作：無法真的執行§4「需呼叫工具」分支①（交付
    # 工具管線）與③（等待結果後做第二輪推理），本輪先以降級文字結束對話，
    # 並清空剛剛暫存的狀態（不會再有人來 resume 這一輪）。若模型本身已經給了
    # 一段簡短引導文字（content 非空），維持原意用它當這一輪的回覆，不疊加
    # 降級說明。
    final_text = content or _tool_pipeline_unavailable_notice(tool_calls)
    if not content:
        yield ("response_chunk", final_text)
    Harness.append_assistant_message(session_id, final_text)
    _clear_pending_reasoning(session_id)
    yield ("end", None)


def resume_with_tool_result(
    session_id: str, tool_results: List[Dict[str, Any]]
) -> Iterator[Event]:
    """
    對應 Architect/Architect.md 循序圖步驟 ⑭–⑰／LLMReasoning.md §4「需呼叫
    工具」分支③：工具管線（Tool/、Guardrails/）執行完成、拿到結果後，結合
    本輪暫存的 pending_reason_content 與 tool_results 做第二輪推理，產生
    最終自然語言回覆。

    目前 Tool/、Guardrails/ 套件都還沒實作，沒有任何呼叫端會呼叫這個函式；
    先把介面（函式簽名、輸入輸出格式）定義出來，讓未來這兩個套件完工時可以
    直接接上，呼叫端（未來的 Tool/ 管線或 Frontend）不需要再改介面。

    Args:
        session_id: 本輪對話的 Session ID，需帶有 process() 暫存的
            pending_reason_content／pending_tool_calls（透過
            Harness.SESSION_STORE.get(session_id) 取得）。
        tool_results: 工具管線回傳的結果列表（格式對應 Tool/ 套件的輸出，
            目前尚未定義）。

    Yields:
        跟 process() 相同的事件格式。

    Raises:
        NotImplementedError: 需等 Tool/、Guardrails/ 套件完成後，才能真正
            組出含工具結果的第二輪 messages 並重新呼叫 LLM.stream_answer()。
    """
    raise NotImplementedError(
        "resume_with_tool_result 尚未實作：需等 Tool/、Guardrails/ 套件完成，"
        "才能組出第二輪推理所需的工具結果訊息並重新呼叫 LLM。"
    )


__all__ = ["process", "resume_with_tool_result"]
