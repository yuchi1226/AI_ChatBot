# -*- coding: utf-8 -*-
"""
Tool/
-----
工具調用判斷模組（Tool Calling Decision Module）。實作
Architect/ToolCalling.md §3、§5、§6：定義工具白名單與 JSON Schema
（§3、§5），並驗證模型實際吐出的 tool_calls 是否合法（§6）。

只涵蓋循序圖步驟⑦「判斷需要調用工具」本身：白名單/參數驗證，以及（由
LLMReasoning/ 執行的）重試機制所需的常數與例外型別。真正執行工具（步驟
⑧–⑬ Tool Pipeline／外部工具／安全守衛）不屬於本套件範圍，留給未來的
Guardrails/ 與工具執行管道實作。

對外只需要：

    import Tool

    definitions = Tool.get_tool_definitions()   # 塞進系統提示詞（System/ 使用）
    Tool.validate_against_catalog(tool_calls)    # 白名單/型態驗證（LLMReasoning/ 使用）
"""

from Tool.catalog import TOOL_CATALOG, ToolSpec, get_tool_definitions
from Tool.config import RETRY_MAX
from Tool.errors import (
    MissingRequiredParameterError,
    ParameterTypeError,
    ToolError,
    UnknownToolError,
)
from Tool.validation import validate_against_catalog

__all__ = [
    "RETRY_MAX",
    "TOOL_CATALOG",
    "MissingRequiredParameterError",
    "ParameterTypeError",
    "ToolError",
    "ToolSpec",
    "UnknownToolError",
    "get_tool_definitions",
    "validate_against_catalog",
]
