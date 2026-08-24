# -*- coding: utf-8 -*-
"""
LLM/ollama_client.py
----------------------
薄薄一層 HTTP 用戶端，只負責跟本機 Ollama 服務的 `/api/chat` 串流端點
溝通：組請求、逐行解析 NDJSON 串流回應。不理解 Harness payload 的格式，
也不理解「思考／回覆」事件語意——那些轉換交給 LLM/llm.py。

使用 httpx 而不是 requests：專案已經透過 gradio 間接依賴 httpx（見
.venv 內已安裝的版本），不用額外加套件，對應 AGENTS.md「優先沿用專案
既有依賴」的原則。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterator, List, Optional

import httpx

from LLM.config import CONNECT_TIMEOUT_SECONDS, OLLAMA_HOST, READ_TIMEOUT_SECONDS
from LLM.errors import OllamaConnectionError, OllamaResponseError

logger = logging.getLogger("llm.ollama_client")

_TIMEOUT = httpx.Timeout(
    connect=CONNECT_TIMEOUT_SECONDS,
    read=READ_TIMEOUT_SECONDS,
    write=CONNECT_TIMEOUT_SECONDS,
    pool=CONNECT_TIMEOUT_SECONDS,
)


def stream_chat(
    model: str,
    messages: List[Dict[str, str]],
    think: bool = True,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Iterator[Dict[str, Any]]:
    """
    呼叫 Ollama `/api/chat`（stream=True），逐一 yield 每一行解析後的 JSON 物件。

    每個物件的形狀（Ollama chat 串流的標準格式）大致為：
        {
          "model": "...", "created_at": "...",
          "message": {"role": "assistant", "content": "...", "thinking": "..."},
          "done": false
        }
    "content" 與 "thinking"（僅思考模型且 think=True 時才有）都是「這次
    新增的片段」，不是累加後的全文；最後一個物件 "done" 為 true，並帶有
    耗時等統計欄位，不含新的 content/thinking。

    Raises:
        OllamaConnectionError: 連不上 Ollama 服務（服務未啟動 / 位址錯誤 / 逾時）。
        OllamaResponseError: HTTP 狀態碼非 200，或串流中某一行帶有 "error" 欄位。
    """
    url = f"{OLLAMA_HOST.rstrip('/')}/api/chat"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": think,
    }
    if tools:
        payload["tools"] = tools

    try:
        with httpx.stream("POST", url, json=payload, timeout=_TIMEOUT) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="ignore")
                raise OllamaResponseError(
                    f"Ollama 回傳 HTTP {response.status_code}: {body[:500]}"
                )

            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("無法解析 Ollama 串流的一行 JSON，略過：%r", line[:200])
                    continue

                if chunk.get("error"):
                    raise OllamaResponseError(str(chunk["error"]))

                yield chunk

    except httpx.ConnectError as exc:
        raise OllamaConnectionError(
            f"無法連線到 Ollama（{OLLAMA_HOST}）。請確認 `ollama serve` "
            f"是否已啟動，以及模型 `{model}` 是否已用 `ollama pull` 下載。"
        ) from exc
    except httpx.TimeoutException as exc:
        raise OllamaConnectionError(f"連線 Ollama（{OLLAMA_HOST}）逾時。") from exc


__all__ = ["stream_chat"]
