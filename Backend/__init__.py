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

    result = Backend.execute_tool(
        Backend.ToolExecutionRequest(
            tool_call_id="call_abc123",
            tool_name="web_search",
            arguments={"query": "台北天氣"},
            execution_mode="http",
        )
    )
    result.is_success, result.content   # 直接可以塞進第二輪推理的 tool 訊息

目前尚未接上 LLMReasoning.resume_with_tool_result()（該函式仍是
NotImplementedError stub，等 Guardrails/ 完工後再一併接線），呼叫端可以
先獨立呼叫 Backend.execute_tool() 驗證這條管線本身的行為。
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
