# -*- coding: utf-8 -*-
"""
LLM/
----
對應 Architect/Architect.md 循序圖裡的「🤖 大語言模型」參與者，實際串接
本機 Ollama 服務（qwen3 系列模型），取代 Frontend/fake_backend.py 的假串流。

對外只需要：

    import LLM

    for event, data in LLM.stream_answer(request_payload):
        ...

`request_payload` 就是 Harness.handle_turn() 回傳的那份完整請求載荷
（見 Architect/PreparatoryPhase.md §4.3）。
"""

from LLM.errors import LLMError, OllamaConnectionError, OllamaResponseError
from LLM.llm import stream_answer

__all__ = [
    "LLMError",
    "OllamaConnectionError",
    "OllamaResponseError",
    "stream_answer",
]
