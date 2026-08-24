# -*- coding: utf-8 -*-
"""
LLM/llm.py
------------
取代 Frontend/fake_backend.py：對應 Architect/Architect.md 循序圖步驟
⑤-⑥（送出完整 Prompt → 深度思考），把 Ollama 的串流回應轉成呼叫端看得懂
的事件。

只負責「跟 Ollama 溝通、把串流 chunk 轉成事件」，不做任何決策——要不要
呼叫工具（步驟⑦判定）、要不要把回覆寫回 Session 歷史，都是 LLMReasoning/
套件的職責（見 Architect/LLMReasoning.md §3.3、§4 與 LLMReasoning/reasoning.py）。
這裡刻意保持「無狀態、無業務判斷」，換模型供應商（例如之後改接
DeepSeek-V3 官方 API）時，只需要重寫這個套件，LLMReasoning/ 的決策邏輯
完全不用動。

只吃 Harness.handle_turn() 組好的完整 request_payload（含系統提示詞、
歷史對話、使用者提問、tools、thinking_mode——見 Architect/PreparatoryPhase.md
§4.3），呼叫本機 Ollama 服務，並把串流回應轉成統一的事件格式：

    ("thought_chunk",  <思考內容片段>)
    ("response_chunk", <最終回覆片段>)
    ("tool_calls",       <本輪模型要求呼叫的完整 tool_calls 列表，僅在非空時送出>)
    ("end",              None)

呼叫端（目前是 LLMReasoning.process()）自行決定要不要轉發 thought_chunk／
response_chunk 給前端顯示，並依有沒有收到 "tool_calls" 事件判斷後續動作；
本模組不做這個判斷。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterator, List, Optional, Tuple

from LLM.config import DEFAULT_THINK, OLLAMA_MODEL
from LLM.errors import LLMError
from LLM.ollama_client import stream_chat

logger = logging.getLogger("llm")

Event = Tuple[str, Optional[Any]]


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
                yield ("response_chunk", content_delta)

            if message.get("tool_calls"):
                tool_calls.extend(message["tool_calls"])

            if chunk.get("done"):
                break

    except LLMError as exc:
        # 連不上 Ollama、模型不存在、回應格式錯誤（含逾時重試後仍失敗，見
        # LLM/ollama_client.py）：不要整個往外拋出讓 Gradio 顯示原始
        # traceback，改成在回覆泡泡裡給使用者看得懂的錯誤訊息，並正常結束
        # 這一輪串流（重新啟用輸入框）。
        logger.error("LLM 串流失敗：%s", exc)
        yield ("response_chunk", f"⚠️ 無法取得模型回覆：{exc}")
        yield ("end", None)
        return

    if tool_calls:
        # 是否要因此走「工具呼叫」分支，交給呼叫端（LLMReasoning.process）
        # 的 decide_action() 判斷，這裡只負責忠實回報模型講了什麼。
        yield ("tool_calls", tool_calls)

    yield ("end", None)


__all__ = ["stream_answer"]
