# -*- coding: utf-8 -*-
"""
Backend/adapters/code_interpreter.py
-----------------------------------------
`code_interpreter` 尚未實作：需要獨立的程式碼執行沙箱環境（隔離的執行
環境、資源限制等），超出本次 Architect/ToolExecution.md 落地範圍。

維持跟 LLMReasoning.resume_with_tool_result()、
LLMReasoning.reasoning._tool_pipeline_unavailable_notice() 一致的既有慣例：
先把介面定義出來、明確告知使用者「尚未上線」，不靜默失敗、也不假裝執行
成功——讓 ADAPTER_REGISTRY 保持完整，Backend/pipeline.py 不需要為「這個
工具還沒做」寫特殊判斷邏輯。
"""

from __future__ import annotations

from Backend.adapters.base import ERROR_NOT_IMPLEMENTED, error_response
from Backend.models import RawToolResponse, ToolExecutionRequest


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    return error_response(
        request.tool_call_id,
        ERROR_NOT_IMPLEMENTED,
        "（這個問題可能需要使用工具「code_interpreter」協助回答，"
        "但工具執行功能尚未上線，暫時無法提供。）",
    )


__all__ = ["execute"]
