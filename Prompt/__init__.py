# -*- coding: utf-8 -*-
"""
Prompt/
-------
系統提示詞緩存（System Prompt Cache）。

對應 Architect/Architect.md 循序圖中的「📜 系统提示詞緩存」參與者，以及
Architect/PreparatoryPhase.md（Harness.md 3.2 節步驟 A「注入系統級指令」
所依賴的資料來源，本檔案是該規格書的完整實作）。

目前為最小可用版本：以行程內記憶體字典存放（等同規格書 §6 所說的「本地
記憶體快取」），之後若要接上真正的 CDN / 外部設定服務，只需要替換
system_prompt_cache.py 內部實作，呼叫端（Harness）的介面不需要變動。
"""

from Prompt.system_prompt_cache import (
    CURRENT_DATE_PLACEHOLDER,
    FALLBACK_PROMPT_BLOCK,
    GLOBAL_DEFAULT_SAFETY_GUARDRAILS,
    get_system_prompt,
)

__all__ = [
    "CURRENT_DATE_PLACEHOLDER",
    "FALLBACK_PROMPT_BLOCK",
    "GLOBAL_DEFAULT_SAFETY_GUARDRAILS",
    "get_system_prompt",
]
