# -*- coding: utf-8 -*-
"""
Backend/adapters/http_request.py
-------------------------------------
`http_request` 工具的通用 HTTP adapter：直接依模型給的 url/method/headers/
body/params 發出請求，對應 §3.1「HTTP 請求」列（逾時 30 秒，逾時或連線
錯誤最多重試 1 次）。

用 httpx（專案既有依賴，見 LLM/ollama_client.py 的說明），不新增套件。
"""

from __future__ import annotations

import logging
import time

import httpx

from Backend.adapters.base import (
    ERROR_CONNECTION,
    ERROR_INVALID_ARGUMENT,
    ERROR_TIMEOUT,
    error_response,
    success_response,
)
from Backend.config import HTTP_RETRY_MAX, HTTP_TIMEOUT_SECONDS
from Backend.models import RawToolResponse, ToolExecutionRequest

logger = logging.getLogger("backend.adapters.http_request")


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    url = request.arguments.get("url")
    method = (request.arguments.get("method") or "GET").upper()
    if not url:
        return error_response(request.tool_call_id, ERROR_INVALID_ARGUMENT, "http_request 缺少必填參數 url。")

    headers = request.arguments.get("headers") or {}
    params = request.arguments.get("params") or {}
    body = request.arguments.get("body")

    attempt = 0
    response = None
    while response is None:
        try:
            response = httpx.request(
                method, url, headers=headers, params=params, json=body, timeout=HTTP_TIMEOUT_SECONDS
            )
        except httpx.TimeoutException as exc:
            if attempt >= HTTP_RETRY_MAX:
                logger.warning("http_request 逾時（已重試 %d 次）：%s", HTTP_RETRY_MAX, exc)
                return error_response(request.tool_call_id, ERROR_TIMEOUT, "工具執行逾時，請檢查網路狀態")
            attempt += 1
            time.sleep(1.0)
        except httpx.HTTPError as exc:
            logger.error("http_request 連線失敗：%s", exc)
            return error_response(request.tool_call_id, ERROR_CONNECTION, "抱歉，服務暫時無法連線，請稍後重試。")

    content_type_header = response.headers.get("content-type", "")
    content_type = "application/json" if "json" in content_type_header else "text/plain"
    try:
        payload_body = response.json() if content_type == "application/json" else response.text
    except ValueError:
        content_type = "text/plain"
        payload_body = response.text

    return success_response(
        request.tool_call_id,
        content_type=content_type,
        body=payload_body,
        provenance_label="Source",
        provenance_value=url,
        http_status_code=response.status_code,
    )


__all__ = ["execute"]
