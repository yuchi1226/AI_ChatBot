# -*- coding: utf-8 -*-
"""
Harness/payload.py
--------------------
對應 Architect/Harness.md 第 3.2 節「請求載荷封裝流程」，並依
Architect/PreparatoryPhase.md 的規格強化「步驟 A 注入系統級指令」這一段：

  步驟 A：注入系統級指令 -> 由呼叫端（Harness.harness）透過
            System.get_system_prompt() 取得範本，再交給本模組渲染。
  步驟 B：結構化提示詞建構 -> render_system_prompt_content()
            - §3 內部「參數填補」：尋找範本中的 {{current_date}} 佔位符並替換；
              §5「範本缺少必要佔位符」時，改為自動於末尾附加「目前日期：...」。
            - §6 大小控制：角色定義＋工具定義＋安全紅線總長度超過
              MAX_SYSTEM_PROMPT_TOKENS 時，先精簡工具描述，仍超出則截斷角色定義。
            - §7 稽核日誌：記錄每次最終產生的系統提示詞。
  步驟 C：上下文綑綁 -> assemble_request()
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from Harness.config import DEFAULT_MODE, MAX_SYSTEM_PROMPT_TOKENS, TIMEZONE_OFFSET_HOURS
from Harness.session import Message
from Harness.text_preprocessing import approx_token_count, truncate_keep_head
from System.system_prompt_cache import CURRENT_DATE_PLACEHOLDER

_TZ = timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))

logger = logging.getLogger("harness.payload")
_audit_logger = logging.getLogger("audit.system_prompt")


def current_datetime_iso() -> str:
    """強制注入當前時間以消除時空模糊（PreparatoryPhase.md §3 內部步驟「參數填補」）。"""
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _escape_placeholder_value(value: str) -> str:
    """
    §7 提示詞注入防護：substitute 進範本的值必須跳脫，避免被解讀成新的樣板語法。
    目前這個值只會是伺服器端產生的日期字串，風險極低，但仍做防禦性處理：
    移除值本身可能帶有的 "{{" / "}}"，避免替換後又意外組出新的佔位符。
    """
    return value.replace("{{", "").replace("}}", "")


def _inject_current_date(text: str, placeholder: str, current_datetime: str) -> Tuple[str, bool]:
    """
    在 text 中尋找 placeholder（預設 "{{current_date}}"）並替換為 current_datetime。

    Returns:
        (替換後文字, 是否有找到並替換)。
    """
    if not text or not placeholder or placeholder not in text:
        return text, False
    safe_value = _escape_placeholder_value(current_datetime)
    return text.replace(placeholder, safe_value), True


def _truncate_tool_definitions(
    tool_definitions: List[Dict[str, Any]], budget_tokens: float
) -> List[Dict[str, Any]]:
    """
    §6：「超出時自動截斷工具描述...確保不超過模型上下文視窗的 30%」。
    把可用的 token 預算平均分給每個工具，超過預算的描述保留頭部（工具名稱、
    用途通常寫在描述最前面）並截斷尾端。
    """
    if not tool_definitions or budget_tokens <= 0:
        return []

    per_tool_budget = budget_tokens / len(tool_definitions)
    truncated: List[Dict[str, Any]] = []
    for tool in tool_definitions:
        tool = dict(tool)
        tool["description"] = truncate_keep_head(tool.get("description", ""), per_tool_budget)
        truncated.append(tool)
    return truncated


def render_system_prompt_content(
    prompt_content: Dict[str, Any], current_datetime: str
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    將範本的 content 區塊（role_definition / safety_guardrails /
    tool_definitions / current_date_placeholder）渲染成：
      - 一段字串，做為 messages[0]（role="system"）的 content。
      - 一份（可能已精簡的）工具定義清單，做為最終 payload 的 "tools" 欄位。

    tool_definitions 不塞進系統提示詞文字內容本身，而是放進最終 payload 的
    "tools" 欄位，避免大型 JSON Schema 灌爆系統提示詞文字；但兩者仍共用同一份
    §6 大小預算（角色 + 工具 + 紅線 <= MAX_SYSTEM_PROMPT_TOKENS）。
    """
    role = prompt_content.get("role_definition", "")
    guardrails = prompt_content.get("safety_guardrails", "")
    tool_definitions = prompt_content.get("tool_definitions", []) or []
    placeholder = prompt_content.get("current_date_placeholder") or CURRENT_DATE_PLACEHOLDER

    role, role_replaced = _inject_current_date(role, placeholder, current_datetime)
    guardrails, guardrails_replaced = _inject_current_date(guardrails, placeholder, current_datetime)

    text = f"{role}\n\n[安全紅線]\n{guardrails}"

    # §5：範本中缺少必要佔位符 -> 自動於末尾附加「目前日期：...」，確保資訊完整。
    if not (role_replaced or guardrails_replaced):
        text += f"\n\n目前日期：{_escape_placeholder_value(current_datetime)}"

    # §6：大小控制，角色 + 工具 + 紅線總長度不得超過 MAX_SYSTEM_PROMPT_TOKENS。
    text_tokens = approx_token_count(text)
    tools_json = json.dumps(tool_definitions, ensure_ascii=False)
    tools_tokens = approx_token_count(tools_json)
    overflow = (text_tokens + tools_tokens) - MAX_SYSTEM_PROMPT_TOKENS

    if overflow > 0:
        # 先精簡工具描述。
        tool_budget = max(tools_tokens - overflow, 0)
        tool_definitions = _truncate_tool_definitions(tool_definitions, tool_budget)
        new_tools_tokens = approx_token_count(json.dumps(tool_definitions, ensure_ascii=False))
        remaining_overflow = overflow - (tools_tokens - new_tools_tokens)

        if remaining_overflow > 0:
            # 工具描述精簡完仍超出，改為截斷角色定義／安全紅線本身。
            text = truncate_keep_head(text, max(text_tokens - remaining_overflow, 0))

        logger.warning(
            "系統提示詞總長度超過 %d tokens，已自動截斷（超出 %.1f tokens）",
            MAX_SYSTEM_PROMPT_TOKENS,
            overflow,
        )

    return text, tool_definitions


def assemble_request(
    session_id: str,
    prompt_block: Dict[str, Any],
    history_messages: List[Message],
    user_query: str,
    stream: bool = True,
    thinking_mode: bool = True,
) -> Dict[str, Any]:
    """
    組合最終發送至 LLM 的請求結構（Harness.md 步驟 C 示意結構）。

    Args:
        session_id: 本次會話的 Session ID。
        prompt_block: System.get_system_prompt() 取得的範本（含 content / metadata）。
        history_messages: 從 Session 拉取的歷史對話陣列。
        user_query: 步驟 2 處理後的純文字輸入（僅透過 "user" 角色傳遞，
            絕不直接拼入系統提示詞——PreparatoryPhase.md §7 提示詞注入防護）。
        stream: 是否以串流方式回應。
        thinking_mode: 是否開啟深度思考。
    """
    current_datetime = current_datetime_iso()
    content = prompt_block.get("content", {})
    system_text, tool_definitions = render_system_prompt_content(content, current_datetime)

    system_message: Message = {"role": "system", "content": system_text}
    messages: List[Message] = [system_message, *history_messages, {"role": "user", "content": user_query}]

    # §7 稽核日誌：記錄每次最終產生的系統提示詞（完整內容）。系統提示詞本身
    # 由伺服器端範本 + 目前時間組成，不含使用者輸入或任何內部識別碼／機密
    # 參數，因此可安全記錄完整內容供合規審查，不需要額外脫敏。
    metadata = prompt_block.get("metadata", {})
    _audit_logger.info(
        "rendered_system_prompt session_id=%s template_id=%s version=%s content=%r",
        session_id,
        prompt_block.get("template_id"),
        metadata.get("version"),
        system_text,
    )

    return {
        "session_id": session_id,
        "messages": messages,
        "tools": tool_definitions,
        "stream": stream,
        "thinking_mode": thinking_mode,
    }


__all__ = [
    "DEFAULT_MODE",
    "assemble_request",
    "current_datetime_iso",
    "render_system_prompt_content",
]
