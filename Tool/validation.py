# -*- coding: utf-8 -*-
"""
Tool/validation.py
----------------------
對應 Architect/ToolCalling.md §5「輸出格式」與 §6「錯誤處理」：驗證模型吐出
的 tool_calls 是否符合 Tool/catalog.py 定義的白名單與 JSON Schema。

跟 LLMReasoning/actions.py 的 validate_tool_calls() 分工：
  - LLMReasoning.actions.validate_tool_calls()：只管「這段 JSON 結構本身
    合不合法」（function.name 是不是非空字串、arguments 是不是 dict 或合法
    JSON 字串），不理解各工具實際定義了什麼參數。
  - 本模組 validate_against_catalog()：假設呼叫端已經先做過上面那層結構
    檢查，這裡專心比對「白名單有沒有這個工具」「必填參數齊不齊全」「型態
    對不對」，這正是 §6 表格「工具名稱不在白名單，或參數型態錯誤」對應的
    重試觸發條件。

刻意不引入 jsonschema 套件：六個工具的 parameters 都是淺層 schema（單層
properties，沒有巢狀 object/array schema），專案 requirements.txt 目前只有
gradio、httpx，AGENTS.md 要求「優先沿用既有依賴」「選擇最簡單、完全滿足
目前需求的實作」，用直接的 isinstance 檢查即可完全滿足規格，不需要新增
依賴。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from Tool.catalog import TOOL_CATALOG
from Tool.errors import MissingRequiredParameterError, ParameterTypeError, UnknownToolError

# JSON Schema "type" 字面值 -> Python 型態的對應。
# bool 是 int 的子類別，需要特別排除，避免 True/False 被誤判成合法的
# integer/number（見 _check_type）。
_JSON_SCHEMA_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _parse_arguments(raw_arguments: Any) -> Dict[str, Any]:
    """
    把 tool_call["function"]["arguments"] 解析成 dict。呼叫端
    （LLMReasoning.actions.validate_tool_calls）已經確保過這個值不是 dict
    就是合法 JSON 字串，這裡不重複做格式檢查，只負責統一成 dict 型態，方便
    後續逐一比對必填/型態。
    """
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if raw_arguments is None:
        return {}
    return json.loads(raw_arguments)


def _check_type(tool_name: str, param_name: str, value: Any, expected_type: str) -> None:
    py_type = _JSON_SCHEMA_TYPE_MAP.get(expected_type)
    if py_type is None:
        # 未知的 schema type 字面值：目前六個工具用不到，保守起見不擋。
        return
    if expected_type in ("integer", "number") and isinstance(value, bool):
        raise ParameterTypeError(
            f"工具「{tool_name}」的參數「{param_name}」型態應為 {expected_type}，實際為 boolean"
        )
    if not isinstance(value, py_type):
        raise ParameterTypeError(
            f"工具「{tool_name}」的參數「{param_name}」型態應為 {expected_type}，"
            f"實際為 {type(value).__name__}"
        )


def _check_required(tool_name: str, arguments: Dict[str, Any], schema: Dict[str, Any]) -> None:
    required = schema.get("required") or []
    missing = [name for name in required if name not in arguments]
    if missing:
        raise MissingRequiredParameterError(
            f"工具「{tool_name}」缺少必填參數：{', '.join(missing)}"
        )

    any_of = schema.get("anyOf") or []
    if any_of:
        satisfied = any(
            all(name in arguments for name in clause.get("required", []))
            for clause in any_of
        )
        if not satisfied:
            option_desc = " 或 ".join(
                "+".join(clause.get("required", [])) for clause in any_of
            )
            raise MissingRequiredParameterError(
                f"工具「{tool_name}」必須至少提供其中一組必填參數：{option_desc}"
            )


def validate_against_catalog(tool_calls: List[Dict[str, Any]]) -> None:
    """
    逐一驗證 tool_calls 是否符合 Tool/catalog.py 的白名單與參數 schema。

    Args:
        tool_calls: 已通過 LLMReasoning.actions.validate_tool_calls() 結構
            檢查的 tool_calls 陣列。

    Raises:
        UnknownToolError: function.name 不在 TOOL_CATALOG 白名單內。
        MissingRequiredParameterError: 缺少必填參數（含 anyOf 條件）。
        ParameterTypeError: 參數型態與 schema 不符。
    """
    for call in tool_calls:
        function = call["function"]
        tool_name = function["name"]

        spec = TOOL_CATALOG.get(tool_name)
        if spec is None:
            whitelist = ", ".join(sorted(TOOL_CATALOG))
            raise UnknownToolError(f"工具「{tool_name}」不在白名單內（可用工具：{whitelist}）")

        arguments = _parse_arguments(function.get("arguments"))
        schema = spec.parameters
        properties = schema.get("properties", {})

        _check_required(tool_name, arguments, schema)

        for param_name, value in arguments.items():
            param_schema = properties.get(param_name)
            if param_schema is None:
                continue  # schema 沒定義的多餘參數：不擋，交給實際執行工具時處理。
            expected_type = param_schema.get("type")
            if expected_type:
                _check_type(tool_name, param_name, value, expected_type)


__all__ = ["validate_against_catalog"]
