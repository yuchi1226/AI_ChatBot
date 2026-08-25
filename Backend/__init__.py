# -*- coding: utf-8 -*-
"""
Backend/
--------
工具執行與結果處理模組（Tool Pipeline）。實作 Architect/ToolExecution.md
步驟⑩–⑬：接收已通過安全審查（Guardrails/ 步驟⑨）的工具呼叫請求，依
execution_mode 分派給對應 adapter 執行，並把雜亂的原始回饋標準化為 LLM
易於理解的結構化文字。

跟 Tool/ 套件的分工：Tool/ 只回答「該不該呼叫、呼叫合不合法」
（ToolCalling.md §5/§6，見 Tool.validate_against_catalog）；Backend/ 回答
「真的去執行、把結果整理好」——兩者共用同一份 Tool/catalog.py 白名單當
tool_name 的資料來源。

對外只需要：

    import Backend

    for event, data in Backend.execute_tool(
        Backend.ToolExecutionRequest(
            tool_call_id="call_abc123",
            tool_name="web_search",
            arguments={"query": "台北天氣"},
            execution_mode="http",
        )
    ):
        if event == "step":
            ...  # Trace.StepEvent，步驟⑩⑪⑫⑬ 的即時進度，轉發給前端思考區
        elif event == "result":
            final_result = data  # Backend.FinalToolResult
            final_result.is_success, final_result.content   # 直接可以塞進第二輪推理的 tool 訊息

Architect/ThoughtPanelStep.md §6.4：execute_tool() 已改為 generator，
在步驟⑩⑪⑫⑬各自的動作*發生的當下*即時 yield 對應的 StepEvent，最終以
("result", FinalToolResult) 收尾——不再是「呼叫一次、同步拿到最終結果」，
呼叫端需要用 for 迴圈迭代。
"""

from Backend.errors import BackendError, ToolConnectionError, ToolTimeoutError, UnknownAdapterError
from Backend.models import ErrorDetail, FinalToolResult, RawToolResponse, ToolExecutionRequest
from Backend.pipeline import execute_tool

__all__ = [
    "BackendError",
    "ErrorDetail",
    "FinalToolResult",
    "RawToolResponse",
    "ToolConnectionError",
    "ToolExecutionRequest",
    "ToolTimeoutError",
    "UnknownAdapterError",
    "execute_tool",
]
