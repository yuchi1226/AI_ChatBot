# -*- coding: utf-8 -*-
"""
Backend/adapters/base.py
---------------------------
各 adapter 共用的工具函式：本地執行的逾時保護、白名單目錄路徑解析、統一
組裝 RawToolResponse 的輔助函式，以及標準化的錯誤代碼常數。

對應 Architect/ToolExecution.md §3.1「執行具體工具」表格：
  - HTTP 請求：逾時 30 秒由各自的 HTTP client（httpx / 第三方 SDK）原生處理，
    這裡不重複包一層；逾時/連線錯誤最多重試 1 次的邏輯留在各 adapter 自己
    的呼叫迴圈裡（見 Backend/adapters/http_request.py、
    Backend/websearch/client.py）。
  - 本地執行：逾時 60 秒、不重試，由這裡的 run_with_local_timeout() 統一
    提供；權限不足時直接拋出 PermissionError，不在這裡攔截。
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeoutError
from typing import Any, Callable, Dict, Optional, TypeVar

from Backend.config import WHITELISTED_DIRS
from Backend.errors import ToolTimeoutError
from Backend.models import ErrorDetail, RawToolResponse

logger = logging.getLogger("backend.adapters")

T = TypeVar("T")

# 共用 thread pool：本地 adapter 的逾時保護用。adapter 呼叫頻率不高，
# 不需要每次呼叫都新開一個 executor（比照 Harness.SESSION_STORE 的
# 模組層級單例作法）。
_LOCAL_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="backend-local-adapter")

# --- 標準化錯誤代碼：Backend/processor.py 依此決定顯示哪段友善錯誤訊息 -----------
ERROR_TIMEOUT = "TIMEOUT"
ERROR_CONNECTION = "CONNECTION_ERROR"
ERROR_EXECUTION = "EXECUTION_ERROR"
ERROR_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
ERROR_INVALID_ARGUMENT = "INVALID_ARGUMENT"


def run_with_local_timeout(func: Callable[..., T], *args: Any, timeout_seconds: float, **kwargs: Any) -> T:
    """
    §3.1「本地執行」逾時保護：把本地 adapter 的實際工作丟進獨立 thread 執行，
    超過 timeout_seconds 秒未完成就拋出 Backend.errors.ToolTimeoutError。

    不用 signal.alarm() 做逾時：那只在 Unix 主執行緒可用，跨平台（含開發者
    常用的 Windows）用 ThreadPoolExecutor 更穩妥。

    PermissionError（或 func 內部拋出的任何其他例外）會透過 future.result()
    原樣重新拋出，不在這裡攔截或轉換——對應 §3.1「本地執行若權限不足，
    直接拋回 PermissionError 至 Harness，不進行重試」。
    """
    future = _LOCAL_EXECUTOR.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=timeout_seconds)
    except _FutureTimeoutError as exc:
        raise ToolTimeoutError(f"本地執行逾時（超過 {timeout_seconds:.0f} 秒）") from exc


def resolve_whitelisted_path(file_id: str) -> str:
    """
    §3.1「本地執行」：「檔案操作須限制於白名單目錄內」。把 file_id（相對路徑
    或絕對路徑）解析成實際檔案路徑，並確認落在 Backend.config.WHITELISTED_DIRS
    其中一個目錄之內；不在白名單內就拋出 PermissionError（不重試，直接往外拋，
    見 run_with_local_timeout 與 Backend/pipeline.py 的說明）。

    file_id 若非絕對路徑，視為相對於第一個白名單目錄。
    """
    if not WHITELISTED_DIRS:
        raise PermissionError("未設定任何白名單目錄，拒絕所有本地檔案存取。")

    candidate = os.path.abspath(
        file_id if os.path.isabs(file_id) else os.path.join(WHITELISTED_DIRS[0], file_id)
    )
    for base in WHITELISTED_DIRS:
        base_abs = os.path.abspath(base)
        if candidate == base_abs or candidate.startswith(base_abs + os.sep):
            return candidate

    raise PermissionError(f"檔案路徑「{file_id}」不在允許存取的白名單目錄內。")


def success_response(
    tool_call_id: str,
    content_type: str,
    body: Any,
    *,
    provenance_label: Optional[str] = None,
    provenance_value: Optional[str] = None,
    http_status_code: Optional[int] = None,
    extra_raw_data: Optional[Dict[str, Any]] = None,
) -> RawToolResponse:
    """
    §3.2：組裝成功時的 RawToolResponse。

    provenance_label/value 對應 §3.3.3「資料來源標記 (Provenance Tagging)」，
    由 Backend/processor.py 讀取並插入 `[Source: ...]` / `[File: ...]`。
    extra_raw_data 供個別 adapter 附加自己需要的線索（例如
    Backend/adapters/file_read.py 標記 kind="file_content"，讓 processor.py
    套用 §4「檔案讀取超過限制」的專屬摘要規則，而非通用頭尾截斷）。
    """
    raw_data: Dict[str, Any] = {"content_type": content_type, "body": body}
    if provenance_label and provenance_value:
        raw_data["provenance"] = {"label": provenance_label, "value": provenance_value}
    if extra_raw_data:
        raw_data.update(extra_raw_data)

    metadata: Dict[str, Any] = {}
    if http_status_code is not None:
        metadata["http_status_code"] = http_status_code
    try:
        metadata["size_bytes"] = len(body) if isinstance(body, (str, bytes)) else len(str(body))
    except TypeError:
        metadata["size_bytes"] = 0

    return RawToolResponse(tool_call_id=tool_call_id, status="success", raw_data=raw_data, metadata=metadata)


def error_response(
    tool_call_id: str,
    code: str,
    message: str,
    *,
    http_status_code: Optional[int] = None,
) -> RawToolResponse:
    """§3.2／§4：組裝失敗時的 RawToolResponse，交給 Backend/processor.py 轉成使用者友善訊息。"""
    metadata: Dict[str, Any] = {}
    if http_status_code is not None:
        metadata["http_status_code"] = http_status_code
    return RawToolResponse(
        tool_call_id=tool_call_id,
        status="error",
        raw_data={"content_type": "text/plain", "body": ""},
        metadata=metadata,
        error=ErrorDetail(code=code, message=message),
    )


__all__ = [
    "ERROR_CONNECTION",
    "ERROR_EXECUTION",
    "ERROR_INVALID_ARGUMENT",
    "ERROR_NOT_IMPLEMENTED",
    "ERROR_TIMEOUT",
    "error_response",
    "resolve_whitelisted_path",
    "run_with_local_timeout",
    "success_response",
]
