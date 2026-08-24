# -*- coding: utf-8 -*-
"""
Tool/errors.py
-----------------
對應 Architect/ToolCalling.md §6「與其他模組的互動介面 - 錯誤處理」：
「若模型輸出的工具名稱不在白名單，或參數型態錯誤，Harness 應觸發重試機制」。

跟 LLMReasoning/errors.py 的 ToolCallFormatError 是不同層級的檢查：
ToolCallFormatError 只管「這段 JSON 結構本身合不合法」（有沒有
function.name、arguments 是不是合法 JSON），不理解各工具實際定義了哪些
參數；ToolError 系列則是「這個工具呼叫符不符合 Tool/catalog.py 定義的白名單
與 schema」，兩者由 LLMReasoning/reasoning.py 依序檢查（先格式、再白名單）。

風格對齊 Harness/errors.py、LLM/errors.py、LLMReasoning/errors.py：各自
獨立的例外基底類別，不跨套件共用繼承關係。
"""

from __future__ import annotations


class ToolError(Exception):
    """Tool/ 套件所有例外的共同基底類別，方便呼叫端一次 except 住。"""


class UnknownToolError(ToolError):
    """工具名稱不在 Tool/catalog.py 的白名單內。"""


class MissingRequiredParameterError(ToolError):
    """缺少該工具定義的必填參數（含 anyOf 條件：一組必填參數全都沒提供）。"""


class ParameterTypeError(ToolError):
    """參數型態與 JSON Schema 定義不符（如 query 給了數字而非字串）。"""
