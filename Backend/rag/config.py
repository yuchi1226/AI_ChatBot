# -*- coding: utf-8 -*-
"""
Backend/rag/config.py
-------------------------
RAG 子系統（BGE-M3 embedding + Qdrant 向量檢索）的常數設定，風格對齊
Backend/config.py。

部署決定（使用者確認）：
  - Qdrant 採 embedded 本地模式：qdrant-client 直接用 path= 讀寫本機磁碟，
    不需要另外啟動 Qdrant 服務或 Docker。QDRANT_STORAGE_PATH 是整個
    Backend/ 套件唯一「真正持久化」的狀態儲存位置。
  - BGE-M3 透過本機 Ollama 的 /api/embed 端點呼叫（`ollama pull bge-m3`），
    沿用專案既有的 Ollama 基礎設施，不新增重量依賴。
"""

from __future__ import annotations

import os

# --- Qdrant（embedded 本地模式）--------------------------------------------------
# 向量資料庫檔案的儲存目錄；換到別的磁碟位置只需要設定環境變數，不用改程式碼。
QDRANT_STORAGE_PATH: str = os.environ.get(
    "RAG_QDRANT_STORAGE_PATH", os.path.join(os.getcwd(), "Backend", "rag", ".qdrant_data")
)
DEFAULT_COLLECTION: str = os.environ.get("RAG_DEFAULT_COLLECTION", "knowledge_base")
# BGE-M3 透過 Ollama 取得的 dense 向量維度固定為 1024。
VECTOR_SIZE: int = int(os.environ.get("RAG_VECTOR_SIZE", "1024"))
DISTANCE_METRIC: str = "COSINE"  # 對應 qdrant_client.models.Distance 的成員名稱

# --- BGE-M3（透過本機 Ollama /api/embed）------------------------------------------
EMBEDDING_MODEL: str = os.environ.get("RAG_EMBEDDING_MODEL", "bge-m3")
EMBEDDING_TIMEOUT_SECONDS: float = float(os.environ.get("RAG_EMBEDDING_TIMEOUT_SECONDS", "30"))

# --- 檢索參數（對應 Tool/catalog.py 的 knowledge_base_search.top_k）---------------
DEFAULT_TOP_K: int = int(os.environ.get("RAG_DEFAULT_TOP_K", "5"))
# 0 = 不過濾分數，交由 LLM 自行判斷檢索結果的相關性；設 >0 可濾掉低分雜訊。
SCORE_THRESHOLD: float = float(os.environ.get("RAG_SCORE_THRESHOLD", "0.0"))

# --- 切塊參數（供 Backend/rag/ingest.py 建置知識庫時使用）-------------------------
CHUNK_SIZE_CHARS: int = int(os.environ.get("RAG_CHUNK_SIZE_CHARS", "500"))
CHUNK_OVERLAP_CHARS: int = int(os.environ.get("RAG_CHUNK_OVERLAP_CHARS", "50"))
