# -*- coding: utf-8 -*-
"""
LLMReasoning/
-------------
LLM 推理與工具呼叫判斷模組。實作 Architect/LLMReasoning.md §3.1–3.3、§4：
組裝完整 Prompt（委派給 Harness）、呼叫 LLM 並啟用深度思考（委派給 LLM
套件）、判定是否需要呼叫工具，並依判定結果流轉到對應分支。

對外只需要：

    import LLMReasoning

    for event, data in LLMReasoning.process(session_id, request_payload):
        ...

`request_payload` 是 Harness.handle_turn() 回傳的完整請求載荷；事件格式與
LLM.stream_answer() 相同（thought_chunk / response_chunk / end），Frontend
可以直接沿用原本的串流渲染邏輯：把呼叫對象從 LLM.stream_answer 換成
LLMReasoning.process，並移除原本手動呼叫 Harness.append_assistant_message
的那一段（現在由本套件內部處理，見 reasoning.py）。
"""

from LLMReasoning.actions import Action, decide_action
from LLMReasoning.errors import LLMReasoningError, ToolCallFormatError
from LLMReasoning.reasoning import process, resume_with_tool_result

__all__ = [
    "Action",
    "LLMReasoningError",
    "ToolCallFormatError",
    "decide_action",
    "process",
    "resume_with_tool_result",
]
