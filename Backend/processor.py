# -*- coding: utf-8 -*-
"""
Backend/processor.py
------------------------
`ToolResponseProcessor`，對應 Architect/ToolExecution.md §3.3 步驟⑫「後執行
處理」與 §4「例外處理矩陣」。把 Backend/adapters/* 交回的 RawToolResponse
轉成 FinalToolResult，供 Backend/pipeline.py 回傳給呼叫端。

三階段處理（§3.3）：
  1. process_response() 入口先判斷 raw.status：
     - "error"（adapter 已標記失敗，如逾時/連線錯誤）-> _process_error()，
       比照 §4「連線逾時」列：「不再進行格式化，直接覆寫內容」。
     - "success" -> 依序跑下面三步。
  2. 結構提取（_extract_structured_text）：JSON 攤平＋陣列取前 N 筆；非
     JSON／解析失敗則退化為純文字（§4 表格第 3 列）；空結果直接回「無相關
     結果」，不觸發截斷（§4 表格第 1 列）。
  3. 內容截斷（_truncate_for_result）：頭尾保留法，硬性限制
     MAX_RESULT_LENGTH_DEFAULT；file_read 的結果改用「摘要 + 前 100 行」
     （§3.3.2 特別規範）。
  4. 格式轉換＋溯源標記（_build_provenance_tag）：插入 `[Source: ...]` /
     `[File: ...]`。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Tuple

from Backend.config import (
    COMPRESSION_RATIO_WARN_THRESHOLD,
    FILE_SUMMARY_HEAD_LINES,
    JSON_ARRAY_HEAD_LIMIT,
    MAX_RESULT_LENGTH_DEFAULT,
)
from Backend.models import FinalToolResult, RawToolResponse

logger = logging.getLogger("backend.processor")

# §3.3.2：中間過長部分以此標記代替。
_MIDDLE_MARKER_TEMPLATE = "...[已省略 {omitted} 字元]..."
# §4 表格第 2 列「原始結果超出限制 (Overflow)」：截斷後另外附加的固定文案。
_OVERFLOW_SUFFIX = "\n... (資料過長已縮減)"
# §4 表格第 4 列「連線逾時」：固定文案，不論 adapter 傳了什麼 message 都覆寫成這句。
_FIXED_ERROR_MESSAGES = {"TIMEOUT": "工具執行逾時，請檢查網路狀態"}
_DEFAULT_ERROR_MESSAGE = "抱歉，工具執行時發生錯誤，請稍後重試。"


def _flatten_json_summary(body: Any) -> str:
    """
    §3.3.1：JSON 攤平，陣列只取前 N 筆。統一支援兩種常見形狀：
      - {"results": [...]}（Backend/adapters/web_search.py、rag_search.py 用）
      - 直接是 list 或 dict
    """
    if isinstance(body, dict) and isinstance(body.get("results"), list):
        results = body["results"]
        head = results[:JSON_ARRAY_HEAD_LIMIT]
        text = json.dumps({"results": head}, ensure_ascii=False, indent=2)
        omitted = len(results) - len(head)
        return text + (f"\n...(其餘 {omitted} 筆已省略)" if omitted > 0 else "")

    if isinstance(body, list):
        head = body[:JSON_ARRAY_HEAD_LIMIT]
        text = json.dumps(head, ensure_ascii=False, indent=2)
        omitted = len(body) - len(head)
        return text + (f"\n...(其餘 {omitted} 筆已省略)" if omitted > 0 else "")

    if isinstance(body, dict):
        return json.dumps(body, ensure_ascii=False, indent=2)

    return str(body)


def _extract_structured_text(raw: RawToolResponse) -> str:
    """§3.3.1 結構提取；§4 表格第 3 列「原始結果非合法 JSON 結構」在這裡退化為純文字。"""
    content_type = raw.raw_data.get("content_type", "text/plain")
    body = raw.raw_data.get("body")

    if body is None or body == "":
        return ""

    if content_type == "application/json":
        if isinstance(body, (dict, list)):
            return _flatten_json_summary(body)
        try:
            parsed = json.loads(body) if isinstance(body, str) else body
        except (TypeError, json.JSONDecodeError):
            logger.warning("raw_data 宣稱 content_type=application/json 但無法解析，改以純文字處理")
            return str(body)
        return _flatten_json_summary(parsed)

    # text/plain 與 binary（後者原則上只會收到路徑或摘要字串，見 §3.2）
    # 都當純文字處理，只去除多餘的空白，保留完整段落。
    return str(body).strip()


def _file_summary_truncate(text: str, raw: RawToolResponse, max_length: int) -> str:
    """
    §3.3.2：「若工具為檔案讀取且超過限制，則僅回傳檔案摘要（如行數、檔案大小）
    與前 100 行內容」，取代一般的頭尾截斷法。
    """
    lines = text.splitlines()
    line_count = len(lines)
    size_bytes = raw.metadata.get("size_bytes", len(text.encode("utf-8")))
    head_lines = lines[:FILE_SUMMARY_HEAD_LINES]
    summary = f"[檔案摘要：共 {line_count} 行，約 {size_bytes} bytes，僅顯示前 {len(head_lines)} 行]\n"
    body = "\n".join(head_lines)
    combined = summary + body
    # 保底：即使前 100 行仍超過硬限制，也不能逾越 max_length。
    return combined[:max_length]


def _head_tail_truncate(text: str, max_length: int) -> str:
    """§3.3.2「頭尾保留法」：保留開頭與結尾，中間以標記取代。"""
    omitted = len(text) - max_length
    marker = _MIDDLE_MARKER_TEMPLATE.format(omitted=omitted)
    budget = max(max_length - len(marker), 0)
    head_len = budget // 2
    tail_len = budget - head_len
    head = text[:head_len]
    tail = text[len(text) - tail_len :] if tail_len > 0 else ""
    return f"{head}{marker}{tail}"


def _truncate_for_result(text: str, raw: RawToolResponse, max_length: int) -> Tuple[str, bool, float]:
    """
    §4 表格第 2 列「原始結果超出限制 (Overflow)」的分派入口：一般結果走
    §3.3.2 頭尾保留法，file_read 的結果走專屬摘要規則。回傳
    (處理後文字, 是否截斷, 截斷後大小/原始大小)。
    """
    if max_length <= 0 or len(text) <= max_length:
        return text, False, 1.0

    if raw.raw_data.get("kind") == "file_content":
        truncated_text = _file_summary_truncate(text, raw, max_length)
    else:
        truncated_text = _head_tail_truncate(text, max_length)

    ratio = len(truncated_text) / len(text) if text else 1.0
    return truncated_text, True, ratio


def _build_provenance_tag(raw: RawToolResponse) -> str:
    """§3.3.3：`[Source: URL]` 或 `[File: path]`，資料來源由 adapter 透過 raw_data["provenance"] 提供。"""
    provenance = raw.raw_data.get("provenance")
    if not provenance or not provenance.get("value"):
        return ""
    label = provenance.get("label", "Source")
    return f"[{label}: {provenance['value']}]"


def _process_error(raw: RawToolResponse) -> FinalToolResult:
    """
    §3.4「錯誤回傳規範」＋§4 例外矩陣：`is_success` 為 false，`content` 填入
    使用者友善錯誤訊息（不直接顯示系統堆疊追蹤）。

    TIMEOUT 一律覆寫成 §4 表格固定的那句文案；其餘錯誤代碼優先採用 adapter
    自己準備的友善訊息（例如 Backend/adapters/web_search.py 針對連線失敗
    給的「搜尋服務暫時無法連線」），沒有的話才退回通用預設訊息。
    """
    code = raw.error.code if raw.error else "UNKNOWN"
    if code in _FIXED_ERROR_MESSAGES:
        message = _FIXED_ERROR_MESSAGES[code]
    elif raw.error and raw.error.message:
        message = raw.error.message
    else:
        message = _DEFAULT_ERROR_MESSAGE

    return FinalToolResult(
        tool_call_id=raw.tool_call_id,
        is_success=False,
        content=message,
        metadata={"error_code": code},
    )


def process_response(
    raw: RawToolResponse, max_result_length: int = MAX_RESULT_LENGTH_DEFAULT
) -> FinalToolResult:
    """
    §3.3–3.4 主入口：把 adapter 回傳的 RawToolResponse 轉成 FinalToolResult。

    Args:
        raw: Backend/adapters/* 產生的原始回應。
        max_result_length: 最終輸出字串長度上限（字元數），對應 §2 輸入物件
            的 max_result_length（由呼叫端動態注入，未提供則用 config.py 預設值）。
    """
    if raw.status == "error":
        return _process_error(raw)

    text = _extract_structured_text(raw)
    original_size = len(text)

    if not text:
        # §4 表格第 1 列：原始結果為空，直接回「無相關結果」，不觸發截斷邏輯。
        return FinalToolResult(
            tool_call_id=raw.tool_call_id,
            is_success=True,
            content="無相關結果",
            metadata={"original_size": 0, "truncated": False},
        )

    body_text, truncated, ratio = _truncate_for_result(text, raw, max_result_length)
    if truncated:
        body_text += _OVERFLOW_SUFFIX

    source_tag = _build_provenance_tag(raw)
    final_text = f"{source_tag}\n{body_text}" if source_tag else body_text

    metadata = {"original_size": original_size, "truncated": truncated}
    if truncated:
        metadata["truncation_ratio"] = f"{ratio * 100:.0f}%"

    compression_ratio = len(final_text) / original_size if original_size else 1.0
    if compression_ratio < COMPRESSION_RATIO_WARN_THRESHOLD:
        logger.warning(
            "tool_result_compression_ratio 過低（%.1f%%），原始資料可能有過多無用雜訊：tool_call_id=%s",
            compression_ratio * 100,
            raw.tool_call_id,
        )

    return FinalToolResult(
        tool_call_id=raw.tool_call_id,
        is_success=True,
        content=final_text,
        metadata=metadata,
    )


__all__ = ["process_response"]
