# -*- coding: utf-8 -*-
"""
LLM/ollama_client.py
----------------------
薄薄一層 HTTP 用戶端，只負責跟本機 Ollama 服務的 `/api/chat` 串流端點
溝通：組請求、逐行解析 NDJSON 串流回應，並依 Architect/LLMReasoning.md §5
「LLM API 逾時 -> 重試最多 2 次（指數退避）」的規格在這一層做重試。不理解
Harness payload 的格式，也不理解「思考／回覆／要不要呼叫工具」的事件語意
——那些轉換交給 LLM/llm.py；「要不要呼叫工具」的決策則交給 LLMReasoning/。

使用 httpx 而不是 requests：專案已經透過 gradio 間接依賴 httpx（見
.venv 內已安裝的版本），不用額外加套件，對應 AGENTS.md「優先沿用專案
既有依賴」的原則。

重試策略的取捨：串流 API 沒辦法「重播」已經送到呼叫端的內容，所以只有在
「這次嘗試完全沒有收到任何一個 chunk」就逾時的情況下才重試整個請求；只要
已經開始吐出內容後才卡住，代表使用者已經看到部分回覆，這時候重試會變成
從頭重講一次、混進舊內容，屬於更糟的使用者體驗——維持原本行為：直接把
錯誤往外拋，交給 LLM/llm.py 轉成友善的錯誤訊息結束這一輪。連線層級的錯誤
（Ollama 服務根本沒啟動）也不重試，因為那通常不是「等一下就會自己好」的
暫時性問題，重試只會讓使用者多等幾秒才看到同一個錯誤。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from LLM.config import (
    API_RETRY_BACKOFF_BASE_SECONDS,
    API_RETRY_MAX,
    CONNECT_TIMEOUT_SECONDS,
    OLLAMA_HOST,
    READ_TIMEOUT_SECONDS,
)
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
        OllamaConnectionError: 連不上 Ollama 服務（服務未啟動 / 位址錯誤），
            或逾時重試 API_RETRY_MAX 次後仍然逾時。
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

    attempt = 0
    while True:
        received_any_chunk = False
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

                    received_any_chunk = True
                    yield chunk
            return

        except httpx.TimeoutException as exc:
            if received_any_chunk or attempt >= API_RETRY_MAX:
                raise OllamaConnectionError(f"連線 Ollama（{OLLAMA_HOST}）逾時。") from exc
            backoff_seconds = API_RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt)
            attempt += 1
            logger.warning(
                "呼叫 Ollama 逾時（尚未收到任何回應內容），%.1fs 後進行第 %d/%d 次重試...",
                backoff_seconds,
                attempt,
                API_RETRY_MAX,
            )
            time.sleep(backoff_seconds)
            continue

        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"無法連線到 Ollama（{OLLAMA_HOST}）。請確認 `ollama serve` "
                f"是否已啟動，以及模型 `{model}` 是否已用 `ollama pull` 下載。"
            ) from exc


__all__ = ["stream_chat"]
