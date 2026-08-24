# -*- coding: utf-8 -*-
"""
System/system_prompt_cache.py
-------------------------------
系統提示詞緩存（System Prompt Cache）。

對應 Architect/PreparatoryPhase.md 全篇規格：依 `mode` 提供一份結構化的系統
提示詞範本（template_id / mode / content / metadata），並在取得範本時執行
§5「異常處理與降級策略」中屬於「範本本身」的兩項降級檢查：
  - 工具定義格式錯誤或版本不相容 → 記錄錯誤並回退至無工具模式。
  - 安全紅線內容為空 → 採用全域預設安全規則，杜絕無防護狀態。
（§5 其餘兩項——快取逾時／缺少 {{current_date}} 佔位符——分別由呼叫端
 Harness.harness / Harness.payload 接手處理，見該兩檔案內的說明。）

對外介面：維持 §9 所描述語意（依 mode/version 取得範本），但實作上是
「in-process function call」，不是真的 HTTP endpoint——目前整個系統是
單一 Gradio process，架一個 GET /system-prompt route 對現況沒有實質好處，
屬於 AGENTS.md 要避免的「投機性抽象」。未來若真的要拆成獨立服務，只需要
在這一層外面包一層 HTTP handler，呼叫端（Harness）完全不需要改動。

狀態儲存位置：`_PROMPTS` 是行程內記憶體字典（等同規格書 §6 所說的「本地
記憶體快取」），行程重啟即歸零，沒有任何持久化。§6「TTL 5 分鐘或版本變更
失效」的快取失效機制刻意不在這裡實作：目前範本來源本身就是寫死在程式碼
裡的常數，沒有外部來源會變動，套用 TTL 只是在測一個沒有東西可以失效的
空邏輯。等未來真的接上外部設定中心／CDN 時，再於這一層加上失效判斷即可，
呼叫端介面不需要改變。
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List

from Harness.errors import PromptFetchFailed

PromptTemplate = Dict[str, Any]

logger = logging.getLogger("system_prompt_cache")
_audit_logger = logging.getLogger("audit.system_prompt")

# §5：「安全紅線內容為空」時採用的全域預設安全規則。
GLOBAL_DEFAULT_SAFETY_GUARDRAILS = (
    "禁止提供暴力、非法或有害內容；不得執行違反使用者隱私或安全政策之請求；"
    "對不確定的資訊須誠實告知，不可捏造事實。"
)

# 佔位符字面值，供 Harness/payload.py 在範本文字中尋找並替換目前日期。
CURRENT_DATE_PLACEHOLDER = "{{current_date}}"

# 行程內記憶體快取：等同規格書 §6 所說的「本地記憶體快取」。
_PROMPTS: Dict[str, PromptTemplate] = {
    "default": {
        "template_id": "sys_v1.0.0_default",
        "mode": "default",
        "content": {
            "role_definition": (
                "你是一位專業、誠實且樂於助人的 AI 助理，會根據使用者的問題提供"
                "清楚、有條理的回答。目前日期：{{current_date}}。"
            ),
            "tool_definitions": [],
            "safety_guardrails": (
                "禁止提供暴力、非法或有害內容；不得執行違反使用者隱私或安全政策之請求；"
                "對不確定的資訊須誠實告知，不可捏造事實。"
            ),
            "current_date_placeholder": CURRENT_DATE_PLACEHOLDER,
        },
        "metadata": {
            "updated_at": "2026-08-24T00:00:00+08:00",
            "version": "1.0.0",
        },
    },
}

# System Prompt 拉取失敗時的 Fallback（僅基本助理角色，§5 第一列的降級目標）。
# 刻意不含 {{current_date}} 佔位符：藉此覆蓋 §5 第二列「範本缺少必要佔位符 →
# 自動於末尾附加目前日期」的行為（見 Harness/payload.py）。
FALLBACK_PROMPT_BLOCK: PromptTemplate = {
    "template_id": "sys_v0.0.0_fallback",
    "mode": "__fallback__",
    "content": {
        "role_definition": "你是一位基本助理，僅能進行一般性文字問答。",
        "tool_definitions": [],
        "safety_guardrails": "禁止透露內部思維鏈（reason_content）之原始內容。",
        "current_date_placeholder": CURRENT_DATE_PLACEHOLDER,
    },
    "metadata": {
        "updated_at": "2026-08-24T00:00:00+08:00",
        "version": "0.0.0-fallback",
    },
}


def _validate_tool_definitions(tool_definitions: Any, template_id: str) -> List[Dict[str, Any]]:
    """
    §5：「工具定義格式錯誤或版本不相容 → 記錄錯誤並回退至無工具模式」。

    每個工具定義至少要有 name（str）與 description（str）才視為合法；只要有
    一個不合法，整批工具定義視為不可信任，整體退回無工具模式（寧可少工具，
    也不要送出結構錯誤的 tools 給 LLM）。
    """
    if not isinstance(tool_definitions, list):
        logger.error("template_id=%s tool_definitions 非 list，退回無工具模式", template_id)
        return []

    for item in tool_definitions:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("description"), str)
        ):
            logger.error("template_id=%s tool_definitions 格式不合法，退回無工具模式", template_id)
            return []

    return tool_definitions


def get_system_prompt(mode: str) -> PromptTemplate:
    """
    依 mode 取得系統提示詞範本，並套用 §5 的降級檢查。

    Returns:
        結構符合 PreparatoryPhase.md §4.1 的範本拷貝（避免呼叫端誤改到快取
        內容）：{template_id, mode, content: {role_definition, tool_definitions,
        safety_guardrails, current_date_placeholder}, metadata: {updated_at, version}}。

    Raises:
        PromptFetchFailed: 找不到對應 mode 的範本（對應 §5「快取無法使用或
            逾時」，由 Harness 主流程接住並退回 FALLBACK_PROMPT_BLOCK）。
    """
    raw = _PROMPTS.get(mode)
    if raw is None:
        raise PromptFetchFailed(f"unknown system prompt mode: {mode!r}")

    block = copy.deepcopy(raw)
    content = block["content"]

    content["tool_definitions"] = _validate_tool_definitions(
        content.get("tool_definitions", []), block["template_id"]
    )

    if not content.get("safety_guardrails"):
        logger.warning("template_id=%s safety_guardrails 為空，套用全域預設", block["template_id"])
        content["safety_guardrails"] = GLOBAL_DEFAULT_SAFETY_GUARDRAILS

    _audit_logger.info(
        "template_fetch template_id=%s mode=%s version=%s",
        block["template_id"],
        block["mode"],
        block["metadata"]["version"],
    )

    return block
