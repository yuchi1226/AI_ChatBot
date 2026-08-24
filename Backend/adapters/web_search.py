# -*- coding: utf-8 -*-
"""
Backend/adapters/web_search.py
---------------------------------
`web_search` 工具的 HTTP adapter，對應 ToolExecution.md §3.1「HTTP 請求」列
（第三方 API／搜尋引擎，逾時 30 秒，逾時或連線錯誤最多重試 1 次）。

實際呼叫哪個搜尋引擎、怎麼重試，交給 Backend/websearch/client.py（目前是
DuckDuckGo，不需要 API Key）；這裡只負責把 Tool/catalog.py 的 web_search
參數（query/region/time_range）轉成呼叫，並把結果／例外轉成 RawToolResponse。
"""

from __future__ import annotations

import logging

from Backend.adapters.base import (
    ERROR_CONNECTION,
    ERROR_EXECUTION,
    ERROR_INVALID_ARGUMENT,
    error_response,
    success_response,
)
from Backend.models import RawToolResponse, ToolExecutionRequest
from Backend.websearch import SearchError, search

logger = logging.getLogger("backend.adapters.web_search")


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    query = request.arguments.get("query")
    if not query:
        return error_response(request.tool_call_id, ERROR_INVALID_ARGUMENT, "web_search 缺少必填參數 query。")

    region = request.arguments.get("region")
    time_range = request.arguments.get("time_range")

    try:
        results = search(query=query, region=region, time_range=time_range)
    except SearchError as exc:
        logger.error("web_search 執行失敗：%s", exc)
        return error_response(request.tool_call_id, ERROR_CONNECTION, "抱歉，搜尋服務暫時無法連線，請稍後重試。")
    except Exception:  # noqa: BLE001 - 任何未預期例外都不能讓 Harness 收到原始 traceback
        logger.exception("web_search 發生未預期錯誤")
        return error_response(request.tool_call_id, ERROR_EXECUTION, "搜尋工具執行時發生錯誤，請稍後再試。")

    return success_response(
        request.tool_call_id,
        content_type="application/json",
        body={"results": results},
        provenance_label="Source",
        provenance_value=f"web_search: {query}",
    )


__all__ = ["execute"]
