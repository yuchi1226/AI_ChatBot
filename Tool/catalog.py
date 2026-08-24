# -*- coding: utf-8 -*-
"""
Tool/catalog.py
------------------
工具白名單 + JSON Schema 定義，對應 Architect/ToolCalling.md §3「工具分類與
觸發條件」。這是整個 Tool/ 套件唯一的資料來源（single source of truth）：

  - System/system_prompt_cache.py 從這裡取得 tool_definitions，塞進系統
    提示詞與送給 LLM 的 payload["tools"]（讓模型知道有哪些工具可用、
    什麼時候該用）。
  - Tool/validation.py 從這裡取得白名單與參數 schema，驗證模型實際吐出的
    tool_calls 是否合法（§6：名稱不在白名單／參數型態錯誤 -> 觸發重試）。

每個工具的 `parameters` 採標準 JSON Schema（OpenAI／Ollama function-calling
慣用格式），"description" 同時帶有 §3 表格的觸發條件說明，讓模型能從系統
提示詞的工具描述直接判斷何時該用——對應 §7「在系統提示詞中明確描述每個
工具的適用場景」的調校建議，不需要另外寫規則程式碼去猜測使用者意圖
（LLMReasoning.md 的既有原則：判斷僅基於模型輸出，不額外規則兜底）。

`database_query` 的必填參數是「§3 表格：sql_statement 或
natural_language_query」，用標準 JSON Schema 的 "anyOf": [{"required": [...]}]
表示「至少滿足其中一種」，Tool/validation.py 看得懂這個結構，不需要另外
自訂欄位。

`knowledge_base_search` 是 Architect/ToolExecution.md 實作時新增的第七個
工具：ToolCalling.md §3 原本的 `file_read` 是「頁碼式擷取」語意（file_id +
start_page/end_page），跟「輸入一段自然語言 query，向量檢索最相似片段」的
RAG 語意不同，硬塞進 file_read 只會讓兩種語意互相打架，所以另開一個工具，
專門對應 Backend/rag/ 子系統（BGE-M3 embedding + Qdrant 向量檢索）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]


def _schema(
    properties: Dict[str, Any],
    required: Optional[List[str]] = None,
    any_of: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    if any_of:
        schema["anyOf"] = any_of
    return schema


_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="web_search",
        description=(
            "搜尋網際網路即時資訊。觸發時機：使用者問題涉及即時資訊、新聞、"
            "天氣、股價，或其他模型內建知識無法回答的未知事實時使用；"
            "不要用在常識問答或創意生成。"
        ),
        parameters=_schema(
            properties={
                "query": {"type": "string", "description": "搜尋關鍵詞"},
                "region": {"type": "string", "description": "地區，如 TW"},
                "time_range": {"type": "string", "description": "時間範圍"},
            },
            required=["query"],
        ),
    ),
    ToolSpec(
        name="file_read",
        description=(
            "讀取使用者已上傳的檔案（PDF、Word、Excel 等）。觸發時機：使用者"
            "問題要求擷取特定段落、統計數據，或比對檔案內容時使用。"
        ),
        parameters=_schema(
            properties={
                "file_id": {"type": "string", "description": "檔案識別碼"},
                "start_page": {"type": "integer", "description": "起始頁"},
                "end_page": {"type": "integer", "description": "結束頁"},
                "keyword_filter": {"type": "string", "description": "關鍵字篩選"},
            },
            required=["file_id", "start_page"],
        ),
    ),
    ToolSpec(
        name="code_interpreter",
        description=(
            "執行程式碼以進行計算、數據分析、繪圖或模擬。觸發時機：使用者"
            "要求精確數值結果、統計分析或繪圖時使用。"
        ),
        parameters=_schema(
            properties={
                "code": {"type": "string", "description": "可執行程式碼"},
                "language": {"type": "string", "description": "Python 或 R"},
                "input_data": {"type": "string", "description": "輸入資料"},
            },
            required=["code", "language"],
        ),
    ),
    ToolSpec(
        name="database_query",
        description=(
            "查詢結構化資料庫（內部知識庫）。觸發時機：問題涉及結構化數據"
            "（如 SQL 資料庫）時使用；sql_statement 與 natural_language_query "
            "至少擇一提供。"
        ),
        parameters=_schema(
            properties={
                "sql_statement": {"type": "string", "description": "SQL 查詢語句"},
                "natural_language_query": {"type": "string", "description": "自然語言查詢"},
                "limit": {"type": "integer", "description": "回傳筆數上限"},
                "order_by": {"type": "string", "description": "排序欄位"},
            },
            any_of=[{"required": ["sql_statement"]}, {"required": ["natural_language_query"]}],
        ),
    ),
    ToolSpec(
        name="file_write",
        description=(
            "產生報告、修改檔案內容或匯出結果。觸發時機：使用者明確要求生成"
            "報告、修改文件內容、匯出結果時使用。"
        ),
        parameters=_schema(
            properties={
                "file_id": {"type": "string", "description": "檔案識別碼"},
                "content": {"type": "string", "description": "新內容"},
                "append_mode": {"type": "boolean", "description": "是否附加"},
            },
            required=["file_id", "content"],
        ),
    ),
    ToolSpec(
        name="http_request",
        description=(
            "呼叫第三方 API（如天氣 API、翻譯 API）。觸發時機：需要呼叫系統本身"
            "未內建、但使用者需求明確指向的外部 API 時使用。"
        ),
        parameters=_schema(
            properties={
                "url": {"type": "string", "description": "請求網址"},
                "method": {"type": "string", "description": "HTTP 方法"},
                "headers": {"type": "object", "description": "HTTP headers"},
                "body": {"type": "object", "description": "請求主體"},
                "params": {"type": "object", "description": "查詢參數"},
            },
            required=["url", "method"],
        ),
    ),
    ToolSpec(
        name="knowledge_base_search",
        description=(
            "在已建置的知識庫中做語意（向量）相似度檢索，回傳最相關的段落。"
            "觸發時機：使用者問題要求「根據知識庫/已匯入文件」回答、或需要"
            "從大量已索引文件中找出語意相關段落時使用；不要用於頁碼式擷取"
            "（那屬於 file_read）或即時網路資訊（那屬於 web_search）。"
        ),
        parameters=_schema(
            properties={
                "query": {"type": "string", "description": "自然語言查詢，將被轉成向量做相似度檢索"},
                "top_k": {"type": "integer", "description": "回傳筆數上限，預設由伺服器端設定決定"},
                "collection": {"type": "string", "description": "指定檢索的知識庫集合名稱，未提供則用預設集合"},
            },
            required=["query"],
        ),
    ),
]

# 白名單本體：name -> ToolSpec，Tool/validation.py 與 get_tool_definitions()
# 共用同一份資料。
TOOL_CATALOG: Dict[str, ToolSpec] = {spec.name: spec for spec in _TOOL_SPECS}


def get_tool_definitions() -> List[Dict[str, Any]]:
    """
    以 Architect/PreparatoryPhase.md §4.1 範本的「平鋪」格式（name/description/
    parameters）回傳工具清單，供 System/system_prompt_cache.py 塞進
    prompt_block["content"]["tool_definitions"]；LLM/llm.py 既有的
    _to_ollama_tools() 會再把這個平鋪格式轉成 Ollama 要的巢狀 function-calling
    結構，這裡不需要重複組裝。
    """
    return [
        {"name": spec.name, "description": spec.description, "parameters": spec.parameters}
        for spec in _TOOL_SPECS
    ]


__all__ = ["TOOL_CATALOG", "ToolSpec", "get_tool_definitions"]
