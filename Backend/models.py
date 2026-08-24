# -*- coding: utf-8 -*-
"""
Backend/models.py
--------------------
把 Architect/ToolExecution.md §2、§3.2、§3.4 的 JSON 範例轉成 dataclass，
當作 Backend/ 套件內部（pipeline.py、processor.py、adapters/*）共用的唯一
資料結構，避免各檔案各自手動拼字典、欄位名稱兜不起來。

三個結構對應規格書三個階段：
  ToolExecutionRequest -> §2   輸入物件（呼叫端交付進來的工具呼叫請求）
  RawToolResponse       -> §3.2 步驟⑪（adapter 執行完的原始回饋）
  FinalToolResult        -> §3.4 步驟⑬（處理完、要回傳給 Harness 的最終結果）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolExecutionRequest:
    """§2 輸入物件。"""

    tool_call_id: str
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "local"  # "http" | "local"
    max_result_length: Optional[int] = None  # 由呼叫端（Harness）動態注入，None 時取 config.py 預設值


@dataclass
class ErrorDetail:
    """§3.2 raw_data 的 error 欄位；code 是 Backend.adapters.base 定義的標準化錯誤代碼。"""

    code: str
    message: str


@dataclass
class RawToolResponse:
    """
    §3.2 步驟⑪：adapter 執行完畢後的統一封裝，保留原始資料完整性與 metadata。

    raw_data 形狀：{"content_type": "application/json"|"text/plain"|"binary",
                    "body": ..., "provenance": {"label": ..., "value": ...} (可選)}
    metadata 形狀：{"execution_time_ms": ..., "http_status_code": ... (可選), "size_bytes": ...}
    """

    tool_call_id: str
    status: str  # "success" | "error"
    raw_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[ErrorDetail] = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"


@dataclass
class FinalToolResult:
    """
    §3.4 步驟⑬：交付給核心調度器（Harness / LLMReasoning）的最終結果，
    LLM 將直接讀取 content 欄位。

    metadata 形狀：{"original_size": ..., "truncated": bool,
                    "truncation_ratio": "67%" (僅 truncated 時有值)}
    """

    tool_call_id: str
    is_success: bool
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    attachments: List[Any] = field(default_factory=list)  # 預留欄位，供未來圖片縮圖等用途


__all__ = ["ErrorDetail", "FinalToolResult", "RawToolResponse", "ToolExecutionRequest"]
