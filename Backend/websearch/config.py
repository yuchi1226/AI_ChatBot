# -*- coding: utf-8 -*-
"""
Backend/websearch/config.py
-------------------------------
web_search 子系統的常數設定，風格對齊 Backend/config.py。

DuckDuckGo 不需要申請 API Key（使用者確認的選擇），所以這裡沒有
API_KEY/endpoint 設定；若未來要換成需要金鑰的搜尋服務（Tavily、Brave
Search 等），只需要改 client.py 的實作並在這裡加上對應設定，
Backend/adapters/web_search.py 的介面不需要變動。
"""

from __future__ import annotations

import os

# 對應 Backend/config.py 的 HTTP_TIMEOUT_SECONDS（§3.1「HTTP 請求」逾時 30 秒），
# 獨立設定是因為 ddgs 套件的逾時參數是自己控制，不透過 httpx.Timeout。
DUCKDUCKGO_TIMEOUT_SECONDS: float = float(os.environ.get("WEBSEARCH_TIMEOUT_SECONDS", "30"))

# §3.1：逾時/連線錯誤最多重試 1 次。
RETRY_MAX: int = 1
RETRY_BACKOFF_BASE_SECONDS: float = 1.0

# §3.3.1：搜尋結果只保留前 5 個連結。
DEFAULT_MAX_RESULTS: int = 5

# ddgs 的 region 參數格式如 "tw-tzh"（台灣繁中）；"wt-wt" 為不分地區。
DEFAULT_REGION: str = os.environ.get("WEBSEARCH_DEFAULT_REGION", "wt-wt")
