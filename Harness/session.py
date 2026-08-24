# -*- coding: utf-8 -*-
"""
Harness/session.py
--------------------
對應 Architect/Harness.md 第 3.1 節「Session ID 管理機制」。

Session 是「會話容器」的唯一識別碼，掛載：
  - history：壓縮後的歷史對話陣列。
  - system_prompt_version：當前使用的系統提示詞版本號。
  - tool_auth_status：工具權限狀態。
  - pending_reason_content／pending_tool_calls：Architect/LLMReasoning.md
    §4「需呼叫工具」分支②新增的暫存欄位，見下方 SessionState 定義說明。

狀態儲存位置：本模組內的行程內（in-memory）字典 `SessionStore._sessions`，
以 threading.Lock 保護並發存取。這是目前單一 Gradio 行程部署下最簡單可行
的實作；規格書允許 Redis 或 Memory 兩種選項，之後若要換成 Redis，只需要
替換 SessionStore 內部實作，呼叫端（Harness.harness、LLMReasoning.reasoning）
的介面不需變動。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from Harness.config import MAX_HISTORY_MESSAGES, SESSION_TTL_SECONDS
from Harness.errors import HistoryCorrupted, invalid_session_error

Message = Dict[str, str]  # {"role": "user" | "assistant", "content": "..."}


@dataclass
class SessionState:
    session_id: str
    history: List[Message] = field(default_factory=list)
    system_prompt_version: Optional[str] = None
    tool_auth_status: Dict[str, bool] = field(default_factory=dict)
    last_active_at: float = field(default_factory=time.time)
    # Architect/LLMReasoning.md §4「需呼叫工具」分支②：暫存本輪的內部推理
    # 草稿（reason_content）與原始 tool_calls，供 Tool/、Guardrails/ 管線
    # 完工後，由 LLMReasoning.resume_with_tool_result() 接手做第二輪推理。
    # 兩者只在「這一輪正在等待工具管線處理」的期間有值，其餘時間應為
    # None（LLMReasoning.process() 在無需工具、或工具管線尚未實作而降級
    # 回覆之後，都會把這兩個欄位清空）。
    pending_reason_content: Optional[str] = None
    pending_tool_calls: Optional[List[Dict[str, Any]]] = None

    def touch(self) -> None:
        self.last_active_at = time.time()

    def is_expired(self, ttl_seconds: int = SESSION_TTL_SECONDS) -> bool:
        return (time.time() - self.last_active_at) > ttl_seconds

    def reset(self) -> None:
        """逾時後視為新會話：保留同一個 session_id，但清空所掛載的狀態。"""
        self.history = []
        self.system_prompt_version = None
        self.tool_auth_status = {}
        self.pending_reason_content = None
        self.pending_tool_calls = None
        self.touch()

    def get_history_messages(self) -> List[Message]:
        """
        回傳歷史對話陣列。若結構毀損（型別不符），拋出 HistoryCorrupted，
        由呼叫端（Harness.harness）接住並清空歷史後以當前 Query 重試。
        """
        for item in self.history:
            if not isinstance(item, dict) or "role" not in item or "content" not in item:
                raise HistoryCorrupted("history item missing role/content")
            if not isinstance(item["content"], str):
                raise HistoryCorrupted("history item content must be str")
        return list(self.history)

    def _append_message(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})
        # 「壓縮」策略：只保留最近 N 則訊息，超過就從最舊的開始丟棄。
        if len(self.history) > MAX_HISTORY_MESSAGES:
            self.history = self.history[-MAX_HISTORY_MESSAGES:]

    def append_user_message(self, content: str) -> None:
        self._append_message("user", content)

    def append_assistant_message(self, content: str) -> None:
        self._append_message("assistant", content)


class SessionStore:
    """行程內記憶體 Session 容器。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _is_valid_uuid(candidate: str) -> bool:
        try:
            uuid.UUID(candidate)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    def resolve(
        self,
        header_session_id: Optional[str] = None,
        body_session_id: Optional[str] = None,
    ) -> Tuple[str, SessionState, bool]:
        """
        依規格書 3.1 節「取得策略」解析 Session：
          1. 優先讀取 Header 的 session id。
          2. 若無，檢查 Body 的 session_id 欄位。
          3. 若皆無，生成新的 UUID v4。

        逾時的 Session 視為新會話：保留同一個 id，但清空掛載的狀態。
        格式不合法的 Session ID 會拋出 HarnessError(INVALID_SESSION)。

        Returns:
            (session_id, session_state, is_new_conversation)
        """
        candidate = header_session_id or body_session_id

        if candidate:
            if not self._is_valid_uuid(candidate):
                raise invalid_session_error()

            with self._lock:
                session = self._sessions.get(candidate)
                if session is not None and not session.is_expired():
                    session.touch()
                    return candidate, session, False

                # 不存在，或已逾時 → 視為新會話，但沿用同一個 id。
                session = SessionState(session_id=candidate)
                self._sessions[candidate] = session
                return candidate, session, True

        new_id = str(uuid.uuid4())
        with self._lock:
            session = SessionState(session_id=new_id)
            self._sessions[new_id] = session
        return new_id, session, True

    def get(self, session_id: str) -> Optional[SessionState]:
        with self._lock:
            return self._sessions.get(session_id)

    def purge_expired(self) -> int:
        """清掉已逾時的 Session，回傳清掉的數量（可供背景排程呼叫）。"""
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
            for sid in expired:
                del self._sessions[sid]
            return len(expired)


# 模組層級單例：整個行程共用同一份 Session 狀態。
SESSION_STORE = SessionStore()
