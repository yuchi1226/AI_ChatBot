# -*- coding: utf-8 -*-
"""
Harness/text_preprocessing.py
------------------------------
對應 Architect/Harness.md 第 2.1 節「純文字處理規範」。

四項處理依序套用：
  1. 編碼標準化：強制 UTF-8，丟棄無法解碼的字元（含無效的 Surrogate Pairs）。
  2. 控制字元過濾：移除 ASCII 控制字元，統一換行為 \\n。
  3. 空白字元壓縮：Tab 轉空格；超過 2 個以上的連續換行壓縮為 2 個。
  4. 長度上限（截斷）：超過 Token 緩衝區預留量時，保留「尾部」最新內容，
     並在截斷處插入標記。

第 2.2 節（檔案轉 Markdown）明確標註「暫不實作」，故本模組僅處理純文字。
"""

from __future__ import annotations

import re

from Harness.config import MAX_INPUT_TOKENS, TRUNCATION_MARKER

# 移除 ASCII 控制字元，但保留 \n（\x0A）；\t 與 \r 會在更早的步驟被處理掉。
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B-\x1F\x7F]")
# 3 個以上的連續換行，壓縮為 2 個。
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")


def _normalize_encoding(text: str) -> str:
    """強制轉換為 UTF-8 編碼，丟棄無法解碼的字元（含無效 Surrogate Pairs）。"""
    return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


def _normalize_line_endings_and_filter_controls(text: str) -> str:
    """統一換行符號為 \\n（Windows \\r\\n → \\n），並移除其餘控制字元。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL_CHAR_RE.sub("", text)


def _compress_whitespace(text: str) -> str:
    """Tab 轉空格；壓縮超過 2 個以上的連續換行。"""
    text = text.replace("\t", " ")
    return _EXCESS_NEWLINES_RE.sub("\n\n", text)


def _approx_token_weight(ch: str) -> float:
    """
    粗略估算單一字元的 token 權重（專案目前未引入正式 tokenizer）：
      - ASCII 字元（英數/標點）約 4 字元 = 1 token。
      - 非 ASCII 字元（中日韓文字等）約 1 字元 = 1 token。
    這是保守估計，之後接上 LLM/ 模組若引入官方 tokenizer，可直接替換此函式。
    """
    return 0.25 if ord(ch) < 128 else 1.0


def approx_token_count(text: str) -> float:
    """
    粗略估算整段文字的 token 數，沿用 `_approx_token_weight` 的字元權重規則。
    供 Harness/payload.py 在做系統提示詞大小控制（PreparatoryPhase.md §6）時
    重複使用，避免同一套估算邏輯散落在兩個模組裡。
    """
    return sum(_approx_token_weight(ch) for ch in text)


def truncate_keep_head(text: str, max_tokens: float) -> str:
    """
    保留「頭部」內容，超過上限就截斷尾端，並附加 `TRUNCATION_MARKER`。

    與 `_truncate_keep_tail`（保留尾部，供使用者輸入使用，因為 LLM 通常對
    結尾記憶較深）方向相反：系統提示詞／工具描述通常是開頭資訊最重要
    （角色定義、工具名稱在前），所以這裡改成保留頭部。
    供 Harness/payload.py 做系統提示詞大小控制（PreparatoryPhase.md §6）使用。
    """
    total = 0.0
    kept = []
    truncated = False
    for ch in text:
        total += _approx_token_weight(ch)
        if total > max_tokens:
            truncated = True
            break
        kept.append(ch)

    result = "".join(kept)
    if truncated:
        result += TRUNCATION_MARKER
    return result


def _truncate_keep_tail(text: str, max_tokens: int) -> str:
    """
    若估算 token 數超過上限，優先保留「尾部」最新內容，
    並於截斷處插入 `TRUNCATION_MARKER` 標記。
    """
    total = 0.0
    kept_reversed = []
    truncated = False
    for ch in reversed(text):
        total += _approx_token_weight(ch)
        if total > max_tokens:
            truncated = True
            break
        kept_reversed.append(ch)

    if not truncated:
        return text

    kept_tail = "".join(reversed(kept_reversed))
    return f"{TRUNCATION_MARKER}{kept_tail}"


def clean_plain_text(text: str, max_tokens: int = MAX_INPUT_TOKENS) -> str:
    """
    套用 2.1 節定義的完整前處理流程，回傳清理後的純文字。

    Args:
        text: 使用者原始輸入（純文字）。
        max_tokens: Token 緩衝區預留量，預設取 Harness/config.py 的設定。

    Returns:
        清理（含必要時截斷）後的文字；若輸入為 None，視為空字串處理。
    """
    if text is None:
        return ""

    text = _normalize_encoding(text)
    text = _normalize_line_endings_and_filter_controls(text)
    text = _compress_whitespace(text)
    text = _truncate_keep_tail(text, max_tokens)
    return text
