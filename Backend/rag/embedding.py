# -*- coding: utf-8 -*-
"""
Backend/rag/embedding.py
----------------------------
把文字轉成向量，透過本機 Ollama 的 `/api/embed` 端點呼叫 BGE-M3
（需先執行 `ollama pull bge-m3`）。

沿用 LLM/config.py 的 OLLAMA_HOST（跟聊天模型共用同一個 Ollama 服務位址，
不重複定義環境變數；沿用 Tool/config.py 提到的「既有跨套件常數引用慣例」），
但逾時秒數／模型名稱是 RAG 子系統自己的設定（Backend/rag/config.py），因為
embedding 呼叫是一次性 request/response，逾時特性跟 LLM/ollama_client.py
的串流聊天不同，不能共用同一組逾時常數。

只回傳 dense 向量：Ollama 的 `/api/embed` 端點不支援 BGE-M3 官方
FlagEmbedding 套件才有的 sparse／ColBERT 多向量輸出（使用者已確認接受這個
取捨）。若未來要換成官方套件以取得完整多向量能力，只需要重寫這個檔案，
Backend/rag/vector_store.py 與呼叫端介面都不需要改。
"""

from __future__ import annotations

import logging
from typing import List

import httpx

from Backend.rag.config import EMBEDDING_MODEL, EMBEDDING_TIMEOUT_SECONDS
from LLM.config import OLLAMA_HOST

logger = logging.getLogger("backend.rag.embedding")


class EmbeddingError(Exception):
    """呼叫 Ollama embedding API 失敗：連不上服務、模型未拉取、或回應格式不符預期。"""


def embed_text(text: str) -> List[float]:
    """把單一段文字轉成向量。Raises: EmbeddingError。"""
    return embed_texts([text])[0]


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    批次把多段文字轉成向量。Ollama `/api/embed` 原生支援陣列輸入，比逐筆
    呼叫有效率，供 Backend/rag/ingest.py 批次建庫時使用。

    Raises:
        EmbeddingError: 連線失敗、逾時，或回應內容缺少 "embeddings" 欄位。
    """
    if not texts:
        return []

    url = f"{OLLAMA_HOST.rstrip('/')}/api/embed"
    try:
        response = httpx.post(
            url,
            json={"model": EMBEDDING_MODEL, "input": texts},
            timeout=EMBEDDING_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise EmbeddingError(f"呼叫 Ollama embedding（模型：{EMBEDDING_MODEL}）逾時。") from exc
    except httpx.HTTPError as exc:
        raise EmbeddingError(
            f"無法連線到 Ollama（{OLLAMA_HOST}），或模型「{EMBEDDING_MODEL}」尚未拉取，"
            f"請確認已執行 `ollama pull {EMBEDDING_MODEL}`。"
        ) from exc

    embeddings = data.get("embeddings")
    if not embeddings:
        raise EmbeddingError(f"Ollama embedding 回應缺少 embeddings 欄位：{data!r}")
    return embeddings


__all__ = ["EmbeddingError", "embed_text", "embed_texts"]
