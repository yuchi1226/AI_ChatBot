# -*- coding: utf-8 -*-
"""
Backend/rag/
------------
RAG（Retrieval-Augmented Generation）子系統：BGE-M3 embedding（透過本機
Ollama）+ Qdrant 向量檢索（embedded 本地模式），支撐 `knowledge_base_search`
工具（Tool/catalog.py 定義的白名單）。

對外只需要：

    from Backend.rag import embed_text, search, ingest_document

    vector = embed_text("台北的知名景點有哪些？")
    results = search("knowledge_base", vector, top_k=5)
    # [{"uuid": ..., "score": ..., "content": ..., "metadata": ...}, ...]
"""

from Backend.rag.embedding import EmbeddingError, embed_text, embed_texts
from Backend.rag.ingest import chunk_text, ingest_document
from Backend.rag.vector_store import VectorStoreError, ensure_collection, search, upsert_chunks

__all__ = [
    "EmbeddingError",
    "VectorStoreError",
    "chunk_text",
    "embed_text",
    "embed_texts",
    "ensure_collection",
    "ingest_document",
    "search",
    "upsert_chunks",
]
