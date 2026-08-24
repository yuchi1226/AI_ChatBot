# -*- coding: utf-8 -*-
"""
Backend/pipeline.py
----------------------
核心調度：`execute_tool()`，對應 Architect/ToolExecution.md 步驟⑩–⑬的完整
流程骨架，也是 Backend/ 套件對外唯一的入口。

前置條件（§2）：呼叫端已完成 Guardrails/ 的權限審查（Architect.md 循序圖
步驟⑨），必要時已取得使用者授權確認；本函式不做任何授權判斷，那是
Guardrails/ 套件（目前尚未實作）的職責。

流程：
    步驟⑩ 查表選 adapter，交付執行
    步驟⑪ adapter 回傳 RawToolResponse（含原始資料與 metadata）
    步驟⑫ Backend.processor.process_response() 做結構提取／截斷／格式化
    步驟⑬ 回傳 FinalToolResult
並在過程中記錄 §5「效能與監控指標」：tool_execution_duration、
truncation_occurred（tool_result_compression_ratio 的告警在 processor.py
內完成，這裡只記錄耗時與是否截斷）。

額外在 FinalToolResult.metadata 寫入 `completed_at`（UTC ISO 時間戳）：
這是 Architect/AgentLoop.md §5「時間敏感資訊」邊界條件的需求——第二輪推理
（LLMReasoning/agent_loop.py 的 is_stale()）需要比對「工具結果是何時取得的」
與目前系統時間，才能判斷是否已超過 1 小時而需要在回覆中註明時效性；
原本只有 execution_time_ms（耗時），沒有絕對時間可供比對，故補上。統一用
UTC 記錄（內部用途，不是要顯示給使用者看的時間，跟 Harness/ 那組面向使用者
的 +08:00 時區顯示無關，故不共用 Harness.config.TIMEZONE_OFFSET_HOURS，
避免 Backend/ 反過來依賴 Harness/）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from Backend.adapters import ADAPTER_REGISTRY
from Backend.config import MAX_RESULT_LENGTH_DEFAULT
from Backend.models import ErrorDetail, FinalToolResult, RawToolResponse, ToolExecutionRequest
from Backend.processor import process_response

logger = logging.getLogger("backend.pipeline")


def _completed_at_iso() -> str:
    """UTC ISO 時間戳，供 AgentLoop.md §5 時效性比對使用（見上方模組說明）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def execute_tool(request: ToolExecutionRequest) -> FinalToolResult:
    """
    執行單一工具呼叫請求，回傳處理完成的 FinalToolResult。

    Raises:
        PermissionError: 本地執行權限不足（§3.1「本地執行若權限不足，直接
            拋回 PermissionError 至 Harness，不進行重試」）。刻意不在這裡
            攔截：呼叫端需要能區分「工具本身執行失敗」（回傳
            is_success=False 的 FinalToolResult，可以直接把 content 講給
            使用者聽）與「需要重新授權才能繼續」（例如觸發 Guardrails/ 的
            使用者授權流程，見 Architect.md 循序圖「需要用戶授權」分支）
            這兩種本質不同的情境。
    """
    adapter = ADAPTER_REGISTRY.get(request.tool_name)
    max_result_length = request.max_result_length or MAX_RESULT_LENGTH_DEFAULT

    if adapter is None:
        logger.error("找不到工具「%s」對應的 adapter（不在 ADAPTER_REGISTRY 內）", request.tool_name)
        raw = RawToolResponse(
            tool_call_id=request.tool_call_id,
            status="error",
            raw_data={"content_type": "text/plain", "body": ""},
            error=ErrorDetail(
                code="UNKNOWN_TOOL", message=f"工具「{request.tool_name}」尚無對應的執行邏輯。"
            ),
        )
        final = process_response(raw, max_result_length)
        final.metadata["completed_at"] = _completed_at_iso()
        return final

    t0 = time.perf_counter()
    raw = adapter(request)  # PermissionError 在這裡不攔截，原樣往外拋給呼叫端。
    elapsed_ms = (time.perf_counter() - t0) * 1000
    raw.metadata.setdefault("execution_time_ms", round(elapsed_ms, 1))

    final = process_response(raw, max_result_length)
    final.metadata["completed_at"] = _completed_at_iso()

    # §5 效能與監控指標。
    logger.info(
        "tool_execution_duration tool=%s tool_call_id=%s duration_ms=%.1f "
        "is_success=%s truncated=%s",
        request.tool_name,
        request.tool_call_id,
        elapsed_ms,
        final.is_success,
        final.metadata.get("truncated"),
    )

    return final


__all__ = ["execute_tool"]
