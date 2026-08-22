# -*- coding: utf-8 -*-
"""
main.py
--------
專案進入點。負責把 Frontend 資料夾加入 sys.path，載入 Gradio 介面並啟動伺服器。

執行方式：
    python main.py

預設會在 http://127.0.0.1:7860 開啟網站。
"""

import os
import sys

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Frontend")
if FRONTEND_DIR not in sys.path:
    sys.path.insert(0, FRONTEND_DIR)

from app import demo, HEAD_JS, CUSTOM_CSS  # noqa: E402


if __name__ == "__main__":
    demo.queue()  # 開啟 queue，讓 generator (yield) 串流輸出可以正常運作
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        head=HEAD_JS,
        css=CUSTOM_CSS,
    )