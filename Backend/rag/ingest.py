# -*- coding: utf-8 -*-
"""
Backend/rag/ingest.py
-------------------------
離線知識庫建置：把一段文字切成固定大小、有重疊的片段（chunk），呼叫
Backend/rag/embedding.py 轉成向量，再寫入 Backend/rag/vector_store.py。

刻意不在對話請求路徑（Backend/adapters/rag_search.py）上呼叫這裡的函式：
ingest 是「事前建置知識庫」的批次工作，跟「使用者問問題時即時檢索」是兩種
不同節奏的操作，混在一起會讓 knowledge_base_search 的逾時／效能特性難以
預期（§3.1 本地執行逾時只有 60 秒，批次 embedding 一大批文件很容易超過）。

目前 Frontend/ 沒有檔案上傳後自動建庫的流程接到這裡，先把介面定義好，
供未來接上檔案上傳、或獨立的建庫腳本呼叫（呼叫端介面不需要再改）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from Backend.rag.config import CHUNK_OVERLAP_CHARS, CHUNK_SIZE_CHARS, DEFAULT_COLLECTION
from Backend.rag.embedding import embed_texts
from Backend.rag.vector_store import upsert_chunks

logger = logging.getLogger("backend.rag.ingest")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> List[str]:
    """
    以固定字元數＋重疊切塊——最簡單可行的切法，符合 AGENTS.md「選擇最簡單、
    完全滿足目前需求的實作」；若之後需要語意/段落感知切塊，只需要替換這個
    函式，Backend/rag/ingest.py 的呼叫端介面（ingest_document）不用改。
    """
    if not text:
        return []
    if chunk_size <= 0:
        return [text]

    step = max(chunk_size - overlap, 1)
    chunks: List[str] = []
    for start in range(0, len(text), step):
        piece = text[start : start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        if start + chunk_size >= len(text):
            break
    return chunks


def ingest_document(
    text: str,
    source: str,
    collection: str = DEFAULT_COLLECTION,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> int:
    """
    切塊 → 批次 embedding → 寫入 Qdrant。

    Args:
        text: 文件全文（已轉成純文字/Markdown；PDF/Word 等原始格式轉換屬於
            Harness §2.2「檔案轉 Markdown」，該節已標註「暫不實作」，本函式
            因此也只接受已經是純文字的內容）。
        source: 溯源標記用的來源名稱（檔名或路徑），寫進每個 chunk 的
            metadata["source"]，供 Backend/processor.py 的 Provenance Tagging
            使用。
        collection: 寫入的 Qdrant collection 名稱。
        extra_metadata: 額外附加到每個 chunk metadata 的欄位（如文件標題、
            上傳時間）。

    Returns:
        實際寫入的 chunk 數量。
    """
    pieces = chunk_text(text)
    if not pieces:
        logger.warning("ingest_document: source=%s 切塊後為空，略過", source)
        return 0

    vectors = embed_texts(pieces)
    chunks = [
        {
            "vector": vector,
            "content": piece,
            "metadata": {"source": source, "chunk_index": idx, **(extra_metadata or {})},
        }
        for idx, (piece, vector) in enumerate(zip(pieces, vectors))
    ]
    upsert_chunks(collection, chunks)
    logger.info("ingest_document: source=%s 寫入 %d 個 chunk 至 collection=%s", source, len(chunks), collection)
    return len(chunks)


__all__ = ["chunk_text", "ingest_document"]
