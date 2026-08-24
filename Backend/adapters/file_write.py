# -*- coding: utf-8 -*-
"""
Backend/adapters/file_write.py
----------------------------------
`file_write` 工具的本地 adapter：白名單目錄內寫檔，逾時 60 秒、不重試，
權限不足時直接拋出 PermissionError（同 file_read.py 的設計理由，見
Backend.adapters.base.resolve_whitelisted_path）。
"""

from __future__ import annotations

import logging
import os

from Backend.adapters.base import (
    ERROR_EXECUTION,
    ERROR_INVALID_ARGUMENT,
    ERROR_TIMEOUT,
    error_response,
    resolve_whitelisted_path,
    run_with_local_timeout,
    success_response,
)
from Backend.config import LOCAL_TIMEOUT_SECONDS
from Backend.errors import ToolTimeoutError
from Backend.models import RawToolResponse, ToolExecutionRequest

logger = logging.getLogger("backend.adapters.file_write")


def _write_file(path: str, content: str, append_mode: bool) -> int:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    mode = "a" if append_mode else "w"
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(content)
    return len(content)


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    file_id = request.arguments.get("file_id")
    content = request.arguments.get("content")
    append_mode = bool(request.arguments.get("append_mode", False))

    if not file_id or content is None:
        return error_response(
            request.tool_call_id, ERROR_INVALID_ARGUMENT, "file_write 缺少必填參數 file_id 或 content。"
        )

    path = resolve_whitelisted_path(file_id)  # PermissionError 不攔截，直接往外拋。

    try:
        written = run_with_local_timeout(
            _write_file, path, content, append_mode, timeout_seconds=LOCAL_TIMEOUT_SECONDS
        )
    except ToolTimeoutError as exc:
        logger.warning("file_write 逾時：%s", exc)
        return error_response(request.tool_call_id, ERROR_TIMEOUT, "工具執行逾時，請檢查網路狀態")
    except Exception:  # noqa: BLE001
        logger.exception("file_write 發生未預期錯誤")
        return error_response(request.tool_call_id, ERROR_EXECUTION, "寫入檔案時發生錯誤，請稍後再試。")

    return success_response(
        request.tool_call_id,
        content_type="text/plain",
        body=f"已成功寫入 {written} 字元至「{file_id}」。",
        provenance_label="File",
        provenance_value=file_id,
    )


__all__ = ["execute"]
