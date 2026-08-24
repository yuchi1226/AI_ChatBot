# -*- coding: utf-8 -*-
"""
Backend/rag/vector_store.py
-------------------------------
封裝 Qdrant（embedded 本地模式：qdrant-client 直接用 path= 讀寫本機磁碟，
不需要另外啟動 Qdrant 服務或 Docker——使用者確認的部署方式）。

這是整個 Backend/ 套件唯一「真正持久化」的狀態儲存位置，見
Backend/rag/config.py 的 QDRANT_STORAGE_PATH：其餘套件（Harness.SESSION_STORE、
System 的提示詞快取）都是行程內記憶體，重啟即歸零；Qdrant 的資料庫檔案則
留在磁碟上，跨行程重啟仍在。

search() 回傳 [{"uuid", "score", "content", "metadata"}, ...]，這正是
使用者需求明確要求的 TOP-K 回傳格式，供 Backend/adapters/rag_search.py
直接組進 RawToolResponse。

延遲匯入 qdrant_client（在函式內部才 import）：requirements.txt 尚未安裝
時，讓 `import Backend` 本身不會整包失敗，只有真的呼叫到 RAG 相關功能才
會需要這個套件——對應 AGENTS.md「避免投機性抽象」的相反面：這裡不是抽象，
是刻意延後一個外部依賴的載入時機。
"""

from __future__ import annotations

import logging
import threading
import uuid as uuid_module
from typing import Any, Dict, List, Optional

from Backend.rag.config import DEFAULT_COLLECTION, DISTANCE_METRIC, QDRANT_STORAGE_PATH, SCORE_THRESHOLD, VECTOR_SIZE

logger = logging.getLogger("backend.rag.vector_store")

_client_lock = threading.Lock()
_client: Any = None  # 延遲初始化的 QdrantClient 單例


class VectorStoreError(Exception):
    """Qdrant 讀寫失敗，含 qdrant-client 尚未安裝的情況。"""


def _get_client() -> Any:
    """
    延遲建立 QdrantClient 單例：embedded 模式的 QdrantClient 會鎖住
    QDRANT_STORAGE_PATH 目錄，整個行程只能有一個實例持有這把鎖，比照
    Harness/session.py 的 SESSION_STORE「模組層級單例 + lock 保護」模式。
    """
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            try:
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise VectorStoreError(
                    "尚未安裝 qdrant-client，請先執行 `pip install qdrant-client`。"
                ) from exc
            _client = QdrantClient(path=QDRANT_STORAGE_PATH)
        return _client


def _existing_collections(client: Any) -> set:
    return {c.name for c in client.get_collections().collections}


def ensure_collection(collection: str, vector_size: int = VECTOR_SIZE) -> None:
    """若集合不存在則建立，供 upsert_chunks() 或建庫腳本呼叫前使用。"""
    from qdrant_client.models import Distance, VectorParams

    client = _get_client()
    if collection in _existing_collections(client):
        return
    logger.info("建立 Qdrant collection：%s（向量維度 %d）", collection, vector_size)
    client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance[DISTANCE_METRIC]),
    )


def upsert_chunks(collection: str, chunks: List[Dict[str, Any]]) -> None:
    """
    寫入向量化後的文字片段，供 Backend/rag/ingest.py 使用。

    Args:
        collection: 目標 collection 名稱。
        chunks: 每筆需含 "vector"（List[float]）、"content"（str）、
            "metadata"（Dict，如 {"source": ..., "chunk_index": ...}）；
            "uuid" 可選，未提供則自動產生一個。
    """
    from qdrant_client.models import PointStruct

    if not chunks:
        return

    client = _get_client()
    ensure_collection(collection, vector_size=len(chunks[0]["vector"]))

    points = [
        PointStruct(
            id=chunk.get("uuid") or str(uuid_module.uuid4()),
            vector=chunk["vector"],
            payload={"content": chunk["content"], "metadata": chunk.get("metadata", {})},
        )
        for chunk in chunks
    ]
    client.upsert(collection_name=collection, points=points)


def search(
    collection: str,
    query_vector: List[float],
    top_k: int,
    score_threshold: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    向量相似度檢索，回傳 TOP-K 結果：
    `[{"uuid": ..., "score": ..., "content": ..., "metadata": ...}, ...]`。

    集合不存在（知識庫尚未 ingest 過任何資料）時回傳空列表，而不是拋例外
    ——這是 Architect/ToolExecution.md §4「原始結果為空」的合法情境，交給
    Backend/processor.py 統一轉成「無相關結果」，不需要在這裡特殊處理。
    """
    client = _get_client()
    if collection not in _existing_collections(client):
        logger.info("Qdrant collection「%s」尚未建立（知識庫可能還沒 ingest），回傳空結果", collection)
        return []

    threshold = SCORE_THRESHOLD if score_threshold is None else score_threshold
    hits = client.query_points(
        collection_name=collection,
        query=query_vector,
        limit=top_k,
        score_threshold=threshold or None,
    ).points

    return [
        {
            "uuid": str(hit.id),
            "score": hit.score,
            "content": (hit.payload or {}).get("content", ""),
            "metadata": (hit.payload or {}).get("metadata", {}),
        }
        for hit in hits
    ]


__all__ = ["VectorStoreError", "ensure_collection", "search", "upsert_chunks"]
