# -*- coding: utf-8 -*-
"""
Backend/adapters/
------------------
`ADAPTER_REGISTRY`：tool_name -> adapter 函式
（`Callable[[ToolExecutionRequest], RawToolResponse]`）。
Backend/pipeline.py 依 Tool/catalog.py 的工具名稱查表分派，對應
Architect/ToolExecution.md §3.1「依 execution_mode 採用不同適配器
(Adapter) 執行底層調用」。

新增一個工具時只需要：
  1. 在 Tool/catalog.py 新增 ToolSpec（白名單/參數 schema）。
  2. 在這個資料夾新增一個 adapter 模組，實作
     `execute(request: ToolExecutionRequest) -> RawToolResponse`。
  3. 在下面的 ADAPTER_REGISTRY 註冊。
不需要改 Backend/pipeline.py。
"""

from __future__ import annotations

from typing import Callable, Dict

from Backend.adapters import (
    code_interpreter,
    database_query,
    file_read,
    file_write,
    http_request,
    rag_search,
    web_search,
)
from Backend.models import RawToolResponse, ToolExecutionRequest

ADAPTER_REGISTRY: Dict[str, Callable[[ToolExecutionRequest], RawToolResponse]] = {
    "web_search": web_search.execute,
    "knowledge_base_search": rag_search.execute,
    "file_read": file_read.execute,
    "file_write": file_write.execute,
    "code_interpreter": code_interpreter.execute,
    "database_query": database_query.execute,
    "http_request": http_request.execute,
}

__all__ = ["ADAPTER_REGISTRY"]
