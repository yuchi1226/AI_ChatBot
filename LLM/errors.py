# -*- coding: utf-8 -*-
"""
LLM/errors.py
--------------
LLM/ 套件對外拋出的例外類型，風格對齊 Harness/errors.py。

這裡的例外都屬於「呼叫本機 Ollama 服務」這一層會發生的問題（連不上、
回應格式錯誤等），跟 Harness/errors.py 的 HarnessError（請求本身不合法，
例如空輸入、Session ID 格式錯誤）是不同層級的錯誤，所以獨立定義，不共用
同一個基底類別。
"""

from __future__ import annotations


class LLMError(Exception):
    """LLM/ 套件所有例外的共同基底類別，方便呼叫端一次 except 住。"""


class OllamaConnectionError(LLMError):
    """連不上本機 Ollama 服務（服務未啟動、位址錯誤、逾時等）。"""


class OllamaResponseError(LLMError):
    """Ollama 回應了非 200 的 HTTP 狀態碼，或串流中某一行帶有 "error" 欄位。"""
