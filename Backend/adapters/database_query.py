# -*- coding: utf-8 -*-
"""
Backend/adapters/database_query.py
---------------------------------------
`database_query` 尚未實作：需要先決定要接哪一種結構化資料庫（以及對應的
連線/權限管理），超出本次 Architect/ToolExecution.md 落地範圍。理由與
Backend/adapters/code_interpreter.py 相同，見該檔案的說明。
"""

from __future__ import annotations

from Backend.adapters.base import ERROR_NOT_IMPLEMENTED, error_response
from Backend.models import RawToolResponse, ToolExecutionRequest


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    return error_response(
        request.tool_call_id,
        ERROR_NOT_IMPLEMENTED,
        "（這個問題可能需要使用工具「database_query」協助回答，"
        "但工具執行功能尚未上線，暫時無法提供。）",
    )


__all__ = ["execute"]
