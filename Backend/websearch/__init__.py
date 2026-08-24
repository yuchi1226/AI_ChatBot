# -*- coding: utf-8 -*-
"""
Backend/websearch/
-------------------
網路搜尋子系統：呼叫 DuckDuckGo（不需 API Key），標準化成
[{"title", "url", "snippet"}, ...] 供 Backend/adapters/web_search.py 使用。

對外只需要：

    from Backend.websearch import search, SearchConnectionError
"""

from Backend.websearch.client import SearchConnectionError, SearchError, search

__all__ = ["SearchConnectionError", "SearchError", "search"]
