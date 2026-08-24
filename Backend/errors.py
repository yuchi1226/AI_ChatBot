# -*- coding: utf-8 -*-
"""
Backend/errors.py
--------------------
Backend/ 套件（Tool Pipeline，實作 Architect/ToolExecution.md 步驟⑩–⑬）
對外拋出的例外型別，風格對齊 Harness/errors.py、LLM/errors.py、
LLMReasoning/errors.py、Tool/errors.py：各自獨立的基底類別，不跨套件共用
繼承關係。

注意：PermissionError（Python 內建例外）刻意不在這裡定義成 Backend 自己的
型別。§3.1「本地執行若權限不足，直接拋回 PermissionError 至 Harness，
不進行重試」——這是規格書明確要求「原樣往外拋、不包裝」的唯一例外，見
Backend/pipeline.py 的 execute_tool() 說明。
"""

from __future__ import annotations


class BackendError(Exception):
    """Backend/ 套件所有例外的共同基底類別，方便呼叫端一次 except 住。"""


class UnknownAdapterError(BackendError):
    """
    tool_name 沒有對應的 adapter。理論上不該發生：呼叫端在交付到 Backend/
    之前，Tool.validate_against_catalog() 已經先擋過白名單；這裡是 Backend/
    套件自己的獨立防呆，不耦合到 Tool/ 的檢查順序（兩個套件各自對「合法
    工具名稱」負責，避免其中一邊漏檢查時整條流程沒有任何防護）。
    """


class ToolTimeoutError(BackendError):
    """
    HTTP 請求逾時（30 秒）或本地執行逾時（60 秒），對應 §3.1 表格與 §4
    例外矩陣「連線逾時 (Timeout)」列。
    """


class ToolConnectionError(BackendError):
    """HTTP 請求連線失敗，且已依 §3.1 重試 1 次仍失敗。"""


__all__ = [
    "BackendError",
    "ToolConnectionError",
    "ToolTimeoutError",
    "UnknownAdapterError",
]
