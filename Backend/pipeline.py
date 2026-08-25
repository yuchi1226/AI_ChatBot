# -*- coding: utf-8 -*-
"""
Backend/pipeline.py
----------------------
核心調度：`execute_tool()`，對應 Architect/ToolExecution.md 步驟⑩–⑬的完整
流程骨架，也是 Backend/ 套件對外唯一的入口。

前置條件（§2）：呼叫端已完成 Guardrails/ 的權限審查（Architect.md 循序圖
步驟⑨），必要時已取得使用者授權確認；本函式不做任何授權判斷，那是
Guardrails/ 套件的職責。

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

Architect/ThoughtPanelStep.md §6.4：`execute_tool()` 由「同步回傳
FinalToolResult」改為 **generator**，在步驟⑩⑪⑫⑬各自的動作*發生的當下*
立即 yield 對應的 StepEvent，而不是執行完畢後一次補發——這是達成「①～⑰
全數真即時串流」的核心改動（Backend/ 是唯一原本整段同步執行完才回傳的
模組）。Trace/ 套件刻意獨立、不依賴 Harness/，這裡引用它不會造成循環依賴。
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Iterator, Tuple

from Backend.adapters import ADAPTER_REGISTRY
from Backend.config import MAX_RESULT_LENGTH_DEFAULT
from Backend.models import ErrorDetail, FinalToolResult, RawToolResponse, ToolExecutionRequest
from Backend.processor import process_response
from Trace.step_events import make_step_event

logger = logging.getLogger("backend.pipeline")

Event = Tuple[str, Any]


def _completed_at_iso() -> str:
    """UTC ISO 時間戳，供 AgentLoop.md §5 時效性比對使用（見上方模組說明）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _describe_raw_data(raw: RawToolResponse) -> str:
    """
    步驟⑪要顯示的原始結果內容。依 Architect/ThoughtPanelStep.md §8 決定，
    內容不做遮蔽或脫敏，完整呈現；binary 類型原則上只會收到路徑或摘要字串
    （Architect/ToolExecution.md §3.2：「原則上不直接傳遞原始 blob，僅回傳
    檔案路徑或 Base64 編碼之摘要」），故此處仍可直接顯示，不需特殊處理。
    """
    content_type = raw.raw_data.get("content_type", "text/plain")
    body = raw.raw_data.get("body")
    if body is None or body == "":
        return "（無原始內容）"
    if content_type == "application/json":
        try:
            return json.dumps(body, ensure_ascii=False, indent=2)
        except TypeError:
            return str(body)
    return str(body)


def execute_tool(request: ToolExecutionRequest) -> Iterator[Event]:
    """
    執行單一工具呼叫請求，即時發射步驟⑩⑪⑫⑬的 StepEvent，最終以
    ("result", FinalToolResult) 收尾。

    Args:
        request: 呼叫端（LLMReasoning/reasoning.py）組好的工具執行請求。

    Yields:
        ("step", StepEvent) — 步驟⑩⑪⑫⑬ 的即時進度事件，供呼叫端原樣轉發
            給前端思考區（`yield from` 或逐一轉送皆可）。
        ("result", FinalToolResult) — 本函式真正的回傳值，作為 generator
            收尾前的唯一一次 "result" 事件；呼叫端應在迭代時取出這個值，
            沿用原本「拿到 FinalToolResult 就塞進 tool_results」的用法。

    Raises:
        PermissionError: 本地執行權限不足（§3.1「本地執行若權限不足，直接
            拋回 PermissionError 至 Harness，不進行重試」）。刻意不在這裡
            攔截：呼叫端需要能區分「工具本身執行失敗」（yield 出
            is_success=False 的 FinalToolResult，可以直接把 content 講給
            使用者聽）與「需要重新授權才能繼續」（例如觸發 Guardrails/ 的
            使用者授權流程，見 Architect.md 循序圖「需要用戶授權」分支）
            這兩種本質不同的情境。由於 generator 的例外會在呼叫端迭代到
            `adapter(request)` 那一次 `next()` 時才真正拋出，此時步驟⑩的
            「running」事件已經送出——呼叫端應在 except 區塊補發步驟⑩～⑬
            的錯誤狀態事件，確保錯誤也走完整的四格顯示（見
            LLMReasoning/reasoning.py 的處理方式）。
    """
    adapter = ADAPTER_REGISTRY.get(request.tool_name)
    max_result_length = request.max_result_length or MAX_RESULT_LENGTH_DEFAULT

    if adapter is None:
        logger.error("找不到工具「%s」對應的 adapter（不在 ADAPTER_REGISTRY 內）", request.tool_name)
        yield "step", make_step_event(
            "tool_execute",
            status="error",
            delta=f"找不到工具「{request.tool_name}」對應的 adapter。",
            meta={"tool_call_id": request.tool_call_id, "tool_name": request.tool_name},
        )
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
        yield "result", final
        return

    # 步驟⑩：執行具體工具 —— 呼叫 adapter 前先送出「開始執行」事件，確保
    # 真即時（事件在動作發生的當下送出，不是執行完畢後才補發）。
    yield "step", make_step_event(
        "tool_execute",
        status="running",
        delta=f"執行「{request.tool_name}」（{request.execution_mode}）…",
        meta={
            "tool_call_id": request.tool_call_id,
            "tool_name": request.tool_name,
            "arguments": request.arguments,  # ThoughtPanelStep.md §8：不遮蔽，原樣顯示。
        },
    )

    t0 = time.perf_counter()
    raw = adapter(request)  # PermissionError 在這裡不攔截，原樣往外拋給呼叫端（見上方 docstring）。
    elapsed_ms = (time.perf_counter() - t0) * 1000
    raw.metadata.setdefault("execution_time_ms", round(elapsed_ms, 1))

    yield "step", make_step_event(
        "tool_execute",
        status="success" if raw.is_success else "error",
        delta=f"耗時 {elapsed_ms:.0f}ms",
        meta={"tool_call_id": request.tool_call_id, "execution_time_ms": round(elapsed_ms, 1)},
    )

    # 步驟⑪：返回原始結果 —— adapter 一回傳就立即送出，不等後續處理。
    yield "step", make_step_event(
        "tool_raw_result",
        status="success" if raw.is_success else "error",
        delta=_describe_raw_data(raw),
        meta={
            "tool_call_id": request.tool_call_id,
            "http_status_code": raw.metadata.get("http_status_code"),
            "size_bytes": raw.metadata.get("size_bytes"),
        },
    )

    # 步驟⑫：後執行處理
    yield "step", make_step_event(
        "tool_post_process",
        status="running",
        delta="結構提取／截斷／格式化中…",
        meta={"tool_call_id": request.tool_call_id},
    )
    final = process_response(raw, max_result_length)
    final.metadata["completed_at"] = _completed_at_iso()
    yield "step", make_step_event(
        "tool_post_process",
        status="success",
        delta=f"截斷比例：{final.metadata.get('truncation_ratio', '無')}",
        meta={"tool_call_id": request.tool_call_id, "truncated": final.metadata.get("truncated", False)},
    )

    # 步驟⑬：返回工具結果
    yield "step", make_step_event(
        "tool_result_ready",
        status="success" if final.is_success else "error",
        delta=final.content,
        meta={"tool_call_id": request.tool_call_id, "is_success": final.is_success},
    )

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

    yield "result", final


__all__ = ["execute_tool"]
