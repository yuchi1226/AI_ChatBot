# -*- coding: utf-8 -*-
"""
Guardrails/rules.py
----------------------
步驟⑨規則式（關鍵字/正則）審查，對應單一 tool_call。純函式、不依賴網路
或模型，任何時候呼叫都是同步、決定性的——這是⑨這一步唯一保證「一定跑得動」
的防線；Guardrails/llm_judge.py 的 LLM 二次複核是規則放行後才加碼的
best-effort 加強，逾時/失敗時不影響這一層的結論（見該模組說明）。

已知限制：純子字串/正則比對抓不到刻意換句話說、委婉包裝、或用其他語言
表達的違規意圖——這部分交給 llm_judge.py 補強；兩層都抓不到的算是這一版
Guardrails 的殘留風險，不是本模組單獨能解決的問題。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlparse

from Guardrails.config import (
    ALLOWED_URL_SCHEMES,
    BLOCKED_HOST_PATTERNS,
    CODE_DANGEROUS_PATTERNS,
    SENSITIVE_KEYWORDS,
    SQL_WRITE_KEYWORDS,
)


@dataclass(frozen=True)
class RejectionReason:
    """
    precheck() 攔截一個 tool_call 時的理由。

    `public_message` 是可以讓使用者看到的通用文案——刻意不透露命中的具體
    規則/關鍵字，避免被當成測試怎麼繞過審查的探針。`category`／
    `internal_detail` 只寫進 log（見 LLMReasoning/reasoning.py 呼叫端），
    供事後稽核。
    """

    category: str
    internal_detail: str
    public_message: str = "很抱歉，這項操作因涉及政策限制，本次無法為您執行。"


_BLOCKED_HOST_RE = [re.compile(pattern, re.IGNORECASE) for pattern in BLOCKED_HOST_PATTERNS]
_CODE_DANGEROUS_RE = [re.compile(pattern, re.IGNORECASE) for pattern in CODE_DANGEROUS_PATTERNS]


def _iter_strings(value: Any) -> Iterator[str]:
    """遞迴取出 tool_call arguments 裡所有字串值，供敏感詞掃描使用。"""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _iter_strings(v)


def _extract(tool_call: Dict[str, Any]) -> "tuple[str, Dict[str, Any]]":
    function = tool_call.get("function", {}) or {}
    name = function.get("name", "")
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        # 理論上呼叫此函式前已通過 §5 結構檢查（validate_tool_calls），
        # arguments 若是字串一定能解析成合法 JSON；這裡僅防呆，解析失敗
        # 就當成一段純文字掃描，不因此讓規則審查本身出錯中斷整輪請求。
        try:
            arguments = json.loads(arguments)
        except (TypeError, ValueError):
            arguments = {"_raw": arguments}
    return name, arguments


def _check_sensitive_keywords(name: str, arguments: Dict[str, Any]) -> Optional[RejectionReason]:
    haystacks: List[str] = [name] + list(_iter_strings(arguments))
    text = " ".join(haystacks).lower()
    for category, keywords in SENSITIVE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text:
                return RejectionReason(
                    category=f"sensitive_keyword:{category}",
                    internal_detail=f"命中關鍵字「{keyword}」（分類：{category}），工具「{name}」",
                )
    return None


def _check_database_query(name: str, arguments: Dict[str, Any]) -> Optional[RejectionReason]:
    if name != "database_query":
        return None
    statement = str(arguments.get("sql_statement") or "").lower()
    if not statement:
        return None
    for keyword in SQL_WRITE_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", statement):
            return RejectionReason(
                category="permission:sql_write",
                internal_detail=f"database_query 帶有寫入/破壞性關鍵字「{keyword}」，超出唯讀查詢用途",
            )
    return None


def _check_http_request(name: str, arguments: Dict[str, Any]) -> Optional[RejectionReason]:
    if name != "http_request":
        return None
    url = str(arguments.get("url") or "")
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_URL_SCHEMES:
        return RejectionReason(
            category="permission:ssrf_scheme",
            internal_detail=f"http_request 使用不允許的 scheme「{parsed.scheme}」，url={url}",
        )
    hostname = parsed.hostname or ""
    for pattern in _BLOCKED_HOST_RE:
        if pattern.match(hostname):
            return RejectionReason(
                category="permission:ssrf_host",
                internal_detail=f"http_request 目標主機「{hostname}」疑似內網/本機位址，url={url}",
            )
    return None


def _check_code_interpreter(name: str, arguments: Dict[str, Any]) -> Optional[RejectionReason]:
    if name != "code_interpreter":
        return None
    code = str(arguments.get("code") or "")
    if not code:
        return None
    for pattern in _CODE_DANGEROUS_RE:
        if pattern.search(code):
            return RejectionReason(
                category="permission:dangerous_code",
                internal_detail=f"code_interpreter 程式碼含高風險樣式「{pattern.pattern}」",
            )
    return None


_CHECKS = (
    _check_sensitive_keywords,
    _check_database_query,
    _check_http_request,
    _check_code_interpreter,
)


def rule_review(tool_call: Dict[str, Any]) -> Optional[RejectionReason]:
    """對單一 tool_call 依序跑完所有規則式檢查，回傳第一個命中的攔截理由（或 None 代表放行）。"""
    name, arguments = _extract(tool_call)
    for check in _CHECKS:
        reason = check(name, arguments)
        if reason is not None:
            return reason
    return None


__all__ = ["RejectionReason", "rule_review"]
