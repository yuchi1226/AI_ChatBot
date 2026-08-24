# -*- coding: utf-8 -*-
"""
Backend/adapters/rag_search.py
----------------------------------
`knowledge_base_search` 工具的 adapter：把 query 轉向量（BGE-M3，透過本機
Ollama）、向 Qdrant 做 TOP-K 相似度檢索，回傳 UUID／分數／內容。

execution_mode 歸類為 "local"：Qdrant 是 embedded 本地模式（純本機磁碟
I/O，無對外網路流量）；呼叫 Ollama embedding 雖然走 HTTP，但目標是本機
服務，性質更接近 §3.1 表格「內部函數」而非「第三方 API」，因此逾時保護
採用 Backend.adapters.base 的本地執行逾時（Backend/config.py
LOCAL_TIMEOUT_SECONDS＝60 秒），不重試。
"""

from __future__ import annotations

import logging

from Backend.adapters.base import (
    ERROR_EXECUTION,
    ERROR_INVALID_ARGUMENT,
    ERROR_TIMEOUT,
    error_response,
    run_with_local_timeout,
    success_response,
)
from Backend.config import LOCAL_TIMEOUT_SECONDS
from Backend.errors import ToolTimeoutError
from Backend.models import RawToolResponse, ToolExecutionRequest
from Backend.rag.config import DEFAULT_COLLECTION, DEFAULT_TOP_K
from Backend.rag.embedding import EmbeddingError, embed_text
from Backend.rag.vector_store import VectorStoreError
from Backend.rag.vector_store import search as vector_search

logger = logging.getLogger("backend.adapters.rag_search")


def _run(query: str, collection: str, top_k: int):
    vector = embed_text(query)
    return vector_search(collection, vector, top_k)


def execute(request: ToolExecutionRequest) -> RawToolResponse:
    query = request.arguments.get("query")
    if not query:
        return error_response(
            request.tool_call_id, ERROR_INVALID_ARGUMENT, "knowledge_base_search 缺少必填參數 query。"
        )

    collection = request.arguments.get("collection") or DEFAULT_COLLECTION
    top_k = request.arguments.get("top_k") or DEFAULT_TOP_K

    try:
        results = run_with_local_timeout(
            _run, query, collection, top_k, timeout_seconds=LOCAL_TIMEOUT_SECONDS
        )
    except ToolTimeoutError as exc:
        logger.warning("knowledge_base_search 逾時：%s", exc)
        return error_response(request.tool_call_id, ERROR_TIMEOUT, "工具執行逾時，請檢查網路狀態")
    except (EmbeddingError, VectorStoreError) as exc:
        logger.error("knowledge_base_search 執行失敗：%s", exc)
        return error_response(
            request.tool_call_id, ERROR_EXECUTION, "抱歉，知識庫檢索服務暫時無法使用，請稍後重試。"
        )
    except Exception:  # noqa: BLE001
        logger.exception("knowledge_base_search 發生未預期錯誤")
        return error_response(request.tool_call_id, ERROR_EXECUTION, "知識庫檢索工具執行時發生錯誤，請稍後再試。")

    return success_response(
        request.tool_call_id,
        content_type="application/json",
        body={"results": results},
        provenance_label="Source",
        provenance_value=f"知識庫檢索（collection={collection}, top_k={top_k}）",
    )


__all__ = ["execute"]
