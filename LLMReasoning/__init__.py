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
        if event == "step":
            ...  # Trace.StepEvent，步驟⑤⑥⑦⑧⑨…的即時進度，轉發給前端思考區
        elif event == "end":
            ...

`request_payload` 是 Harness.handle_turn() 回傳的完整請求載荷。若判定需要
呼叫工具，process() 會依序做 Guardrails.precheck()（步驟⑨）與
Backend.execute_tool()（步驟⑩–⑬）、再流轉進 Architect/AgentLoop.md
§3.1–3.4 的第二輪推理（見 reasoning.py 的 resume_with_tool_result() 與
agent_loop.py）；confidence_score／cited_sources／reasoning_summary 併入
步驟⑰ StepEvent 的 meta，供前端「信心分數 < 0.6 顯示免責聲明」的 UI 使用。
"""

from LLMReasoning.actions import Action, decide_action
from LLMReasoning.agent_loop import SecondRoundResult
from LLMReasoning.errors import LLMReasoningError, ToolCallFormatError
from LLMReasoning.reasoning import process, resume_with_tool_result

__all__ = [
    "Action",
    "LLMReasoningError",
    "SecondRoundResult",
    "ToolCallFormatError",
    "decide_action",
    "process",
    "resume_with_tool_result",
]
