# -*- coding: utf-8 -*-
"""
fake_backend.py
----------------
後端尚未完成，這裡用假資料模擬「思考鏈 (thought)」與「最終回覆 (response)」的
逐字串流輸出，事件格式對齊附錄六建議的 JSON schema：

    {"event": "thought_chunk",  "data": "..."}
    {"event": "response_chunk", "data": "..."}
    {"event": "end",            "data": None}

之後接上真正後端（SSE / WebSocket）時，只需要把 stream_answer() 換成
真正呼叫後端 API 並逐段 yield 同樣格式的 (event, data) tuple 即可，
上層 Gradio 介面完全不用改動。
"""

import time
import random


# 針對關鍵字準備幾組比較貼切的假回覆，其餘問題則用通用模板
_CANNED_ANSWERS = {
    "天氣": "根據示範資料，今天大致是多雲時晴，氣溫約 24°C 到 29°C，午後有零星降雨機率，建議出門可以帶把小雨傘。",
    "gradio": "Gradio 是一個可以用純 Python 快速打造機器學習 / AI 應用網頁介面的框架，內建 Chatbot、Textbox、Markdown 等元件，很適合拿來做這種左右雙欄的對話展示介面。",
    "python": "Python 是一個語法簡潔、生態系豐富的程式語言，常被用在資料科學、後端開發與自動化腳本，也是 Gradio、PyTorch 等許多 AI 工具的主要語言。",
}

_DEFAULT_ANSWER_TEMPLATE = (
    "這是針對「{q}」所產生的示範回覆。目前串接的是假資料，"
    "尚未接上真正的後端服務；等後端 API 完成後，只要替換 fake_backend.py "
    "裡的邏輯，前端介面完全不需要修改。"
)


def _pick_answer(user_message: str) -> str:
    for keyword, answer in _CANNED_ANSWERS.items():
        if keyword.lower() in user_message.lower():
            return answer
    return _DEFAULT_ANSWER_TEMPLATE.format(q=user_message)


def _build_thought(user_message: str) -> str:
    """組出一段看起來像 Chain-of-Thought 的假思考內容"""
    steps = [
        f"1. 解析使用者輸入：「{user_message}」，先確認語意與意圖。",
        "2. 檢查是否有相關的背景知識或關鍵字可以比對。",
        "3. 篩選出與問題最相關的資訊片段，排除不相關的雜訊。",
        "4. 組織回答的邏輯順序，先講結論、再補充細節。",
        "5. 檢查回答是否清楚、精簡，並符合使用者可能的期待。",
        "6. 產生最終回覆內容，準備輸出給使用者。",
    ]
    return "\n".join(steps)


def stream_answer(user_message: str):
    """
    模擬串流輸出。依序 yield (event, data)：
      - ("thought_chunk", 單一字元)  x N
      - ("response_chunk", 單一字元) x N
      - ("end", None)

    使用逐字元 yield 是為了在 Gradio 端可以做出「打字機」效果，
    並確保第一個字元能在極短時間內（<500ms）送出。
    """
    thought_text = _build_thought(user_message)
    answer_text = _pick_answer(user_message)

    # 思考鏈：速度快一點，模擬「推理中」的感覺
    for ch in thought_text:
        yield ("thought_chunk", ch)
        time.sleep(random.uniform(0.005, 0.018))

    # 最終回覆：稍微慢一點，比較像打字機
    for ch in answer_text:
        yield ("response_chunk", ch)
        time.sleep(random.uniform(0.015, 0.035))

    yield ("end", None)