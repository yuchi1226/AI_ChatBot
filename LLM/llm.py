# -*- coding: utf-8 -*-
"""
LLM/llm.py
------------
取代 Frontend/fake_backend.py：對應 Architect/Architect.md 循序圖步驟
⑤-⑧（送出完整 Prompt → 深度思考 → 判斷不需要工具 → 直接回覆這條分支）。

只吃 Harness.handle_turn() 組好的完整 request_payload（含系統提示詞、
歷史對話、使用者提問、tools、thinking_mode——見 Architect/PreparatoryPhase.md
§4.3），呼叫本機 Ollama 服務，並把串流回應轉成跟 fake_backend.stream_answer()
完全相同的事件格式，讓 Frontend/app.py 只需要換一行呼叫對象，其餘串流／
打字機顯示邏輯完全不用改：

    ("thought_chunk",  <思考內容片段>)
    ("response_chunk", <最終回覆片段>)
    ("end",            None)

工具呼叫這條分支（步驟 ⑨ 以後：Guardrails 審核 → 實際執行工具 → 把結果
餵回模型做第二輪推理）尚未實作，屬於 Tool/、Guardrails/ 套件的範圍
（AGENTS.md：先讓最小版本端到端可用，工具管線之後再疊上去）。目前如果
模型回傳 tool_calls，這裡只會記錄警告、用一段說明文字充當回覆，不會
真的去呼叫任何工具，也不會把 tool_calls 送回模型做第二輪推理。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

from LLM.config import DEFAULT_THINK, OLLAMA_MODEL
from LLM.errors import LLMError
from LLM.ollama_client import stream_chat

logger = logging.getLogger("llm")

Event = Tuple[str, Optional[str]]


def _to_ollama_tools(tool_definitions: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
    """
    把 Harness 範本的 tool_definitions（name/description/parameters 平鋪
    格式，見 Architect/PreparatoryPhase.md §4.1）轉成 Ollama `/api/chat`
    要求的 tools 格式（OpenAI function-calling 風格的巢狀結構）。

    目前 System/system_prompt_cache.py 的 default 範本 tool_definitions
    是空陣列，這個轉換函式先做好，等之後真的掛上工具定義、也做完
    Tool/Guardrails 管線後即可直接生效，呼叫端不需要再改。
    """
    if not tool_definitions:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
            },
        }
        for tool in tool_definitions
    ]


def _tool_calls_placeholder(tool_calls: List[Dict[str, Any]]) -> str:
    """
    「Tool/ 尚未實作」的降級行為：模型想呼叫工具，但目前沒有工具執行管線
    可以接手處理，於是記錄警告並回傳一段對使用者誠實的說明文字，而不是
    靜默吞掉、留一顆永遠空白的回覆泡泡給使用者。
    """
    names = ", ".join(
        call.get("function", {}).get("name", "unknown") for call in tool_calls
    ) or "unknown"
    logger.warning(
        "模型要求呼叫工具（%s），但 Tool/Guardrails 管線尚未實作，略過執行。", names
    )
    return f"（這個問題可能需要使用工具「{names}」協助回答，但工具執行功能尚未上線，暫時無法提供。）"


def stream_answer(request_payload: Dict[str, Any]) -> Iterator[Event]:
    """
    對應 fake_backend.stream_answer() 的介面，但吃的是 Harness 組好的
    完整 request_payload，而不是單純一段清理後的文字——這是這次整合要
    修正的地方：先前 Frontend/app.py 只把
    request_payload["messages"][-1]["content"]（也就是使用者這句話）
    丟給 fake_backend，Harness 組好的系統提示詞／歷史對話其實完全沒被
    用到；現在改成把整份 payload 交給這裡，系統提示詞與歷史對話才會
    真的送進模型。

    Args:
        request_payload: Harness.handle_turn() 回傳的 payload，需包含
            "messages"（system + history + user）、"tools"、"thinking_mode"。
    """
    messages = request_payload.get("messages", [])
    thinking_mode = request_payload.get("thinking_mode", DEFAULT_THINK)
    tools = _to_ollama_tools(request_payload.get("tools") or [])

    response_acc = ""
    tool_calls: List[Dict[str, Any]] = []

    try:
        for chunk in stream_chat(
            model=OLLAMA_MODEL,
            messages=messages,
            think=bool(thinking_mode),
            tools=tools,
        ):
            message = chunk.get("message") or {}

            thinking_delta = message.get("thinking")
            if thinking_delta:
                yield ("thought_chunk", thinking_delta)

            content_delta = message.get("content")
            if content_delta:
                response_acc += content_delta
                yield ("response_chunk", content_delta)

            if message.get("tool_calls"):
                tool_calls.extend(message["tool_calls"])

            if chunk.get("done"):
                break

    except LLMError as exc:
        # 連不上 Ollama、模型不存在、回應格式錯誤：不要整個往外拋出讓
        # Gradio 顯示原始 traceback，改成在回覆泡泡裡給使用者看得懂的
        # 錯誤訊息，並正常結束這一輪串流（重新啟用輸入框）。
        logger.error("LLM 串流失敗：%s", exc)
        yield ("response_chunk", f"⚠️ 無法取得模型回覆：{exc}")
        yield ("end", None)
        return

    if tool_calls and not response_acc:
        # 模型只給了 tool_calls、完全沒有 content：補一段說明文字，讓
        # 使用者至少知道發生了什麼事，而不是看到一顆永遠空白的回覆泡泡。
        yield ("response_chunk", _tool_calls_placeholder(tool_calls))

    yield ("end", None)


__all__ = ["stream_answer"]
