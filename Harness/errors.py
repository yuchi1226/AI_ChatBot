# -*- coding: utf-8 -*-
"""
Harness/errors.py
------------------
對應 Architect/Harness.md 第 4 節「例外處理與錯誤碼」。

只有 EMPTY_CONTENT 與 INVALID_SESSION 兩種錯誤會「拒絕請求」，以
HarnessError 的形式往外拋給呼叫端（例如 Frontend）處理。

PROMPT_FETCH_FAIL 與 HISTORY_CORRUPTED 屬於「可自我修復」的情境
（啟用 Fallback 提示詞 / 清除歷史後以當前 Query 重試），不會中斷流程，
因此各自定義成內部例外類別，由 Harness 主流程接住、記錄 log 後繼續執行，
不會变成 HarnessError 往外拋出。
"""

from __future__ import annotations


class HarnessError(Exception):
    """會導致請求被拒絕的錯誤（對應規格書表格中 HTTP 4xx 的兩種情境）。"""

    def __init__(self, code: str, http_status: int, user_message: str):
        self.code = code
        self.http_status = http_status
        self.user_message = user_message
        super().__init__(f"[{code}] {user_message}")


def empty_content_error() -> HarnessError:
    """純文字淨長度為 0 → 400 EMPTY_CONTENT。"""
    return HarnessError(
        code="EMPTY_CONTENT",
        http_status=400,
        user_message="請輸入有效內容",
    )


def invalid_session_error() -> HarnessError:
    """Session ID 格式錯誤 → 400 INVALID_SESSION。"""
    return HarnessError(
        code="INVALID_SESSION",
        http_status=400,
        user_message="會話識別碼格式錯誤，請重新建立會話",
    )


class PromptFetchFailed(Exception):
    """System Prompt 拉取失敗（500 PROMPT_FETCH_FAIL，內部處理用）。"""


class HistoryCorrupted(Exception):
    """歷史對話序列化失敗（500 HISTORY_CORRUPTED，內部處理用）。"""
