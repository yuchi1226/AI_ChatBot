# -*- coding: utf-8 -*-
"""
Backend/websearch/client.py
------------------------------
呼叫 DuckDuckGo 網路搜尋（透過 `ddgs` 套件——duckduckgo_search 專案改名後的
現行套件名稱），對應使用者的決定：web_search 不需要申請 API Key。標準化
回傳為 [{"title", "url", "snippet"}, ...]，交給
Backend/adapters/web_search.py 包成 RawToolResponse。

延遲匯入 `ddgs`（在函式內部才 import），避免 requirements.txt 還沒
`pip install ddgs` 時，整個 Backend/ 套件的 import 鏈就直接失敗——沿用
Backend/rag/vector_store.py 對 qdrant-client 的同一套處理方式。

逾時／重試對應 Architect/ToolExecution.md §3.1「HTTP 請求」列：逾時 30 秒、
逾時或連線錯誤最多重試 1 次。ddgs 的例外型別隨版本變動、不保證能穩定區分
「逾時」與「其他連線錯誤」，這裡統一當成暫時性錯誤處理、重試後仍失敗才
往外拋 SearchConnectionError，交給 Backend/adapters/web_search.py 轉成
§4 表格的友善錯誤訊息。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from Backend.websearch.config import (
    DEFAULT_MAX_RESULTS,
    DEFAULT_REGION,
    DUCKDUCKGO_TIMEOUT_SECONDS,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_MAX,
)

logger = logging.getLogger("backend.websearch.client")


class SearchError(Exception):
    """Backend/websearch/ 套件所有例外的共同基底類別。"""


class SearchConnectionError(SearchError):
    """呼叫 DuckDuckGo 失敗，且已重試 RETRY_MAX 次仍失敗（逾時或其他連線問題）。"""


def _run_query(query: str, region: Optional[str], time_range: Optional[str], max_results: int) -> List[Dict[str, Any]]:
    from ddgs import DDGS

    with DDGS(timeout=DUCKDUCKGO_TIMEOUT_SECONDS) as ddgs:
        raw_results = ddgs.text(
            query,
            region=region or DEFAULT_REGION,
            timelimit=time_range,
            max_results=max_results,
        )
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
            }
            for item in raw_results
        ]


def search(
    query: str,
    region: Optional[str] = None,
    time_range: Optional[str] = None,
    max_results: int = DEFAULT_MAX_RESULTS,
) -> List[Dict[str, Any]]:
    """
    Args:
        query: 搜尋關鍵詞（對應 Tool/catalog.py 的 web_search.query）。
        region: 地區代碼，對應 ddgs 的 region（如 "tw-tzh"）；未提供時用
            DEFAULT_REGION（不分地區）。
        time_range: 時間範圍，對應 ddgs 的 timelimit（"d"/"w"/"m"/"y"）；
            不合法的值由 ddgs 自行忽略，這裡不額外驗證。
        max_results: 回傳筆數上限，預設對應 §3.3.1「僅保留前 5 個連結」。

    Raises:
        SearchConnectionError: 重試 RETRY_MAX 次仍失敗。
    """
    attempt = 0
    last_exc: Optional[Exception] = None

    while attempt <= RETRY_MAX:
        try:
            return _run_query(query, region, time_range, max_results)
        except Exception as exc:  # noqa: BLE001 - ddgs 例外型別隨版本變動，統一當暫時性錯誤處理
            last_exc = exc
            if attempt >= RETRY_MAX:
                break
            backoff = RETRY_BACKOFF_BASE_SECONDS * (2**attempt)
            logger.warning(
                "DuckDuckGo 搜尋失敗（第 %d/%d 次嘗試）：%s，%.1fs 後重試",
                attempt + 1,
                RETRY_MAX + 1,
                exc,
                backoff,
            )
            time.sleep(backoff)
            attempt += 1

    raise SearchConnectionError(f"DuckDuckGo 搜尋失敗：{last_exc}") from last_exc


__all__ = ["SearchConnectionError", "SearchError", "search"]
