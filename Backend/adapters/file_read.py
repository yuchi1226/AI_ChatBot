# -*- coding: utf-8 -*-
"""
Backend/adapters/file_read.py
---------------------------------
`file_read` 工具的本地 adapter，對應 §3.1「本地執行」列：檔案操作限制於
白名單目錄內（Backend.adapters.base.resolve_whitelisted_path），逾時 60 秒、
不重試；權限不足時直接拋出 PermissionError（不在這裡攔截，見
Backend/pipeline.py 的說明）。

只支援純文字/Markdown 檔案的行範圍讀取：Tool/catalog.py 的 start_page 在
純文字檔沒有「頁」的概念，這裡簡化成「行號」；PDF/Word 等格式轉換屬於
Harness §2.2「檔案轉 Markdown」，該節已標註「暫不實作」，本 adapter 因此
也只處理已經是純文字的檔案。

extra_raw_data 標記 kind="file_content"，讓 Backend/processor.py 在內容
超過 max_result_length 時，套用 §3.3.2「檔案讀取專屬摘要規則」（回傳行數/
檔案大小摘要 + 前 100 行），而不是一般的頭尾截斷法。
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

logger = logging.getLogger("backend.adapters.file_read")


def _read_lines(path: str, start_line: int, end_line) -> str:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()
    start_idx = max(start_line - 1, 0)
    end_idx = end_line if end_line else len(lines)
    return "".join(lines[start_idx:end_idx])


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    file_id = request.arguments.get("file_id")
    start_page = request.arguments.get("start_page") or 1
    end_page = request.arguments.get("end_page")

    if not file_id:
        return error_response(request.tool_call_id, ERROR_INVALID_ARGUMENT, "file_read 缺少必填參數 file_id。")

    path = resolve_whitelisted_path(file_id)  # PermissionError 不攔截，直接往外拋。

    try:
        content = run_with_local_timeout(
            _read_lines, path, start_page, end_page, timeout_seconds=LOCAL_TIMEOUT_SECONDS
        )
    except ToolTimeoutError as exc:
        logger.warning("file_read 逾時：%s", exc)
        return error_response(request.tool_call_id, ERROR_TIMEOUT, "工具執行逾時，請檢查網路狀態")
    except FileNotFoundError:
        return error_response(request.tool_call_id, ERROR_EXECUTION, f"找不到檔案「{file_id}」。")
    except Exception:  # noqa: BLE001
        logger.exception("file_read 發生未預期錯誤")
        return error_response(request.tool_call_id, ERROR_EXECUTION, "讀取檔案時發生錯誤，請稍後再試。")

    return success_response(
        request.tool_call_id,
        content_type="text/plain",
        body=content,
        provenance_label="File",
        provenance_value=file_id,
        extra_raw_data={"kind": "file_content"},
    )


__all__ = ["execute"]
