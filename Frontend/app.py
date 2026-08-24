# -*- coding: utf-8 -*-
"""
Frontend/app.py
----------------
左右雙欄 AI 對話網站 (Gradio 實作，後端串接 LLMReasoning/ 模組呼叫本機 Ollama)
"""

import html
import os
import sys

import gradio as gr

# 確保專案根目錄（AI_ChatBot/）在 sys.path 上，這樣不論是透過 main.py
# 啟動，還是直接 `python Frontend/app.py` 執行，都能 `import Harness`。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import Harness
import LLMReasoning


# ----------------------------------------------------------------------------
# 樣式 (CSS) - 經過重新設計與高度對齊
# ----------------------------------------------------------------------------
CUSTOM_CSS = """
/* ================================================================
   整體視覺
   ================================================================ */
.gradio-container {
    max-width: 1440px !important;
    width: min(1440px, calc(100vw - 40px)) !important;
    margin: 0 auto !important;
    padding: 28px 20px 36px !important;
    box-sizing: border-box;
}

body {
    background: var(--background-fill-primary);
}

#app_header {
    margin: 0 0 18px 0;
    padding: 4px 2px 0;
}

#app_title {
    margin: 0 !important;
    font-size: 28px !important;
    line-height: 1.2 !important;
    font-weight: 750 !important;
    letter-spacing: -0.02em;
}

#app_subtitle {
    margin-top: 7px !important;
    color: var(--body-text-color-subdued) !important;
    font-size: 14px !important;
}

/* ================================================================
   主畫面：左右欄採固定 grid，比 scale 更穩定
   左右欄永遠各自佔滿相同的整體高度
   ================================================================ */
#main_layout {
    display: grid !important;
    grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr) !important;
    gap: 18px !important;
    align-items: stretch !important;
    height: 720px !important;
    min-height: 720px !important;
    max-height: 720px !important;
    margin: 0 !important;
    /* 保護整體版面：不管內層（聊天訊息／思考內容）長出什麼奇怪的寬高，
       都不允許撐破這個 720px 的格線容器，避免把輸入框、範例按鈕擠到
       別的欄位去。內層真正需要捲動的地方各自有自己的 overflow-y:auto。 */
    overflow: hidden !important;
}

#main_layout > .gr-column {
    min-width: 0 !important;
    width: auto !important;
    height: 100% !important;
    max-height: 100% !important;
    min-height: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
}

#left_panel,
#right_panel {
    min-width: 0 !important;
    min-height: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    box-sizing: border-box !important;
    /* 真正的破圖成因：Gradio 的 Column 元件（.column class）本身預設
       flex-wrap 是 wrap。平常這是為了讓 Column 在螢幕太窄時能自動換行，
       但這裡是 flex-direction:column，wrap 的方向是「換到旁邊那一欄」
       （cross axis 是水平的）。當第一個子元素（聊天框）回答完後，內容
       實際需要的高度超過欄位可用的 720px，瀏覽器在做 wrap 判斷時，會先
       用「還沒套用 flex-shrink 之前」的原始內容高度去判斷要不要換行，
       發現放不下就把聊天框自己獨立算成第一欄，接著把輸入框、範例問題
       按鈕擠成「第二欄」，畫面上就變成疊在思考欄前面、被推到右邊。
       用 flex-wrap: nowrap 強制鎖成單一欄，聊天框才會真的被同一欄裡的
       輸入框、範例問題按鈕擠壓、乖乖用 min-height:0 縮小，而不是整個
       跑去開新的一欄。 */
    flex-wrap: nowrap !important;
    /* 同上：左／右欄本身也要裁切，這樣即使 gr.Chatbot 內部元件的高度／
       寬度計算跑掉，也只會被裁掉多出來的部分，不會把同一欄後面的
       輸入框、範例問題按鈕，或旁邊的思考欄推擠變形。 */
    overflow: hidden !important;
}

#left_panel {
    display: flex !important;
    flex-direction: column !important;
}

#right_panel {
    display: flex !important;
    flex-direction: column !important;
}

/* ================================================================
   聊天框：固定佔滿左欄剩餘高度，不被輸入區擠壓
   ================================================================ */
#chatbot_main {
    flex: 1 1 auto !important;
    min-width: 0 !important;
    min-height: 0 !important;
    height: 100% !important;
    max-height: 100% !important;
    width: 100% !important;
    max-width: 100% !important;
    /* Gradio Chatbot 內部用 position:absolute 的包裹層把訊息區塊撐滿父層，
       這裡明確給 position:relative 當作那層 absolute 的定位基準，避免它
       找不到夠近的定位祖先、跑去撐滿更外層的容器，把版面撐壞。 */
    position: relative !important;
    border-radius: 16px !important;
    border: 1px solid var(--border-color-primary) !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.055) !important;
    overflow: hidden !important;
    background: var(--background-fill-primary) !important;
}

/* Gradio Chatbot 內部的訊息捲動容器（.panel-wrap / .bubble-wrap）：明確
   鎖死高度並交出捲動權，不讓訊息（尤其是回答完後突然變長的那一則）把
   #chatbot_main 的外框撐大，進而擠壓同一欄的輸入框／範例問題按鈕，或
   把版面推到右側思考欄去。 */
#chatbot_main > div,
#chatbot_main .wrap,
#chatbot_main .panel-wrap,
#chatbot_main .bubble-wrap {
    min-width: 0 !important;
    min-height: 0 !important;
    max-width: 100% !important;
    height: 100% !important;
    max-height: 100% !important;
}

#chatbot_main .panel-wrap,
#chatbot_main .bubble-wrap {
    overflow-y: auto !important;
    overflow-x: hidden !important;
}

#chatbot_main .message {
    line-height: 1.7 !important;
}

/* 訊息內文若出現一長串不會換行的文字（網址、程式碼、hash 等），也不能
   撐開整欄的寬度，一律強制換行並限制在欄寬內。 */
#chatbot_main .message-wrap,
#chatbot_main .message,
#chatbot_main pre,
#chatbot_main code {
    min-width: 0 !important;
    max-width: 100% !important;
    overflow-wrap: anywhere !important;
}

#chatbot_main pre {
    overflow-x: auto !important;
}

/* ================================================================
   右側思考區：直接填滿整個右欄，因此與左欄總高度一致
   ================================================================ */
#thought_panel {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    height: 100% !important;
    width: 100% !important;
    overflow: hidden !important;
    box-sizing: border-box !important;
    border: 1px solid var(--border-color-primary) !important;
    border-radius: 16px !important;
    background: var(--background-fill-secondary) !important;
    padding: 0 !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.045) !important;
}

.thought-scroll-inner {
    /* 這裡故意不設 overflow-y:auto——真正負責捲動的是 Gradio HTML 元件
       自己的 .html-container（由 gr.HTML(min_height="100%", max_height=
       "100%", autoscroll=True) 這幾個參數驅動，見下方 build_demo()）。
       這一層維持 height:100%（讓 .thought-empty 的置中效果在內容還很短
       時仍然生效），內容一旦變長，會自然撐出這個 100% 的框，交給外層
       .html-container 的 overflow-y:auto 去捲動——Gradio 內建的
       autoscroll 邏輯也是往上找「最近一個 overflow:auto/scroll 的祖先」
       來捲動，如果這裡自己開一個獨立的捲動區，Gradio 反而會找不到真正
       在捲動的地方，導致捲不動或抓不到底部。 */
    width: 100%;
    height: 100%;
    padding: 22px;
    box-sizing: border-box;
    font-size: 14px;
    line-height: 1.75;
    font-family: 'Cascadia Mono', 'SFMono-Regular', Consolas, monospace;
    white-space: normal;
    word-break: break-word;
    overflow-wrap: anywhere;
}

.thought-empty {
    color: var(--body-text-color-subdued);
    font-style: italic;
    display: flex;
    justify-content: center;
    align-items: center;
    text-align: center;
    height: 100%;
    padding: 24px;
    box-sizing: border-box;
}

/* ================================================================
   輸入區：固定在左欄底部，不改變左欄寬度
   ================================================================ */
.input-group {
    flex: 0 0 auto !important;
    width: 100% !important;
    box-sizing: border-box !important;
    margin-top: 14px !important;
    padding: 5px !important;
    border-radius: 14px !important;
    border: 1px solid var(--border-color-primary) !important;
    background: var(--background-fill-primary) !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.05) !important;
}

.input-group > .gr-row {
    width: 100% !important;
    margin: 0 !important;
}

.input-group textarea,
.input-group textarea:focus {
    border: none !important;
    box-shadow: none !important;
    min-height: 48px !important;
}

#send_btn {
    min-width: 52px !important;
    height: 48px !important;
    border: 0 !important;
    border-radius: 10px !important;
    background: var(--primary-600) !important;
    color: white !important;
    font-size: 20px !important;
    font-weight: 700 !important;
    transition: transform .15s ease, filter .15s ease, opacity .15s ease;
}

#send_btn:hover {
    filter: brightness(0.96);
    transform: translateY(-1px);
}

#send_btn:active {
    transform: translateY(0);
}

/* ================================================================
   範例問題：寬度由 grid 決定，按鈕不會把欄位撐變形
   ================================================================ */
#example-row {
    flex: 0 0 auto !important;
    width: 100% !important;
    margin-top: 12px !important;
    display: grid !important;
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 8px !important;
}

#example-row button {
    width: 100% !important;
    min-width: 0 !important;
    min-height: 42px !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    border-radius: 12px !important;
    padding: 7px 12px !important;
    border: 1px solid var(--border-color-primary) !important;
    background: var(--background-fill-secondary) !important;
    transition: all .15s ease;
}

#example-row button:hover {
    border-color: var(--primary-500) !important;
    transform: translateY(-1px);
}

/* ================================================================
   第二個 Tab：說明內容
   ================================================================ */
#about_panel {
    max-width: 1000px;
    margin: 0 auto;
}

/* ================================================================
   RWD：窄螢幕改成上下排列，避免左右欄被壓縮變形
   ================================================================ */
@media (max-width: 900px) {
    .gradio-container {
        width: min(100vw - 24px, 720px) !important;
        padding: 20px 12px 28px !important;
    }

    #main_layout {
        grid-template-columns: 1fr !important;
        height: auto !important;
        min-height: 0 !important;
    }

    #left_panel,
    #right_panel {
        height: auto !important;
        min-height: 0 !important;
    }

    #chatbot_main {
        height: 560px !important;
        flex: none !important;
    }

    #thought_panel {
        height: 420px !important;
        min-height: 420px !important;
        flex: none !important;
    }

    #example-row {
        grid-template-columns: 1fr !important;
    }
}
"""

# ----------------------------------------------------------------------------
# 前端 JavaScript
# ----------------------------------------------------------------------------
# 原本這裡自己刻了一套 MutationObserver 去監控 #thought_panel、手動記錄
# 捲動位置、模擬「黏底」效果。拆掉的原因：實際測試發現完全不會動、
# 也滑不動——追下去才發現 Gradio 的 gr.HTML 元件本身就有 autoscroll 參數
# （見 build_demo() 裡 thought_html = gr.HTML(...) 那段），而且 Gradio
# 自己的實作方式是「往上找最近一個 overflow:auto/scroll 的祖先」來捲動；
# 我們之前塞給 .thought-scroll-inner 的 overflow-y:auto 反而讓真正在捲動
# 的地方變成一個 Gradio 找不到的內層節點，導致內建的 autoscroll 抓不到、
# 我們自己刻的那套也因為節點被整個置換而亂掉——兩套邏輯互相打架。
# 現在直接交給 Gradio 內建機制處理，不需要任何自訂 JS，也不用維護一份
# 容易在節點置換時出錯的手刻捲動邏輯。
HEAD_JS = ""

# ----------------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------------
def render_thought_html(thought_text: str) -> str:
    if not thought_text:
        inner = '<span class="thought-empty">等待思考過程…</span>'
    else:
        inner = html.escape(thought_text).replace("\n", "<br>")
    return f'<div class="thought-scroll-inner">{inner}</div>'

def _extract_text(content) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return "" if content is None else str(content)

EXAMPLE_QUESTIONS = [
    "今天天氣如何？適合出門嗎？",
    "可以簡單介紹一下 Gradio 嗎？",
    "為什麼很多 AI 工具都用 Python 開發？",
]

# ----------------------------------------------------------------------------
# 對話邏輯
# ----------------------------------------------------------------------------
def user_submit(user_message, history):
    user_message = (user_message or "").strip()
    if not user_message:
        return history, "", render_thought_html("")
    history = history + [{"role": "user", "content": user_message}]
    return history, "", render_thought_html("")

def disable_inputs():
    """同時停用輸入框與發送按鈕"""
    return gr.update(interactive=False), gr.update(interactive=False)

def bot_response(history, session_id):
    if not history or history[-1]["role"] != "user":
        # 如果無效，立刻重新啟用輸入元件
        yield history, render_thought_html(""), gr.update(interactive=True), gr.update(interactive=True), session_id
        return

    user_message = _extract_text(history[-1]["content"])

    # ---- Harness 步驟 1-6：前處理 + Session 管理 + 請求載荷組裝 ----
    try:
        session_id, request_payload = Harness.handle_turn(user_message, session_id=session_id)
    except Harness.HarnessError as exc:
        # EMPTY_CONTENT / INVALID_SESSION：拒絕本次請求，於對話中顯示錯誤訊息。
        # INVALID_SESSION 額外把 session_id 重置為 None，讓下一輪重新建立會話。
        if exc.code == "INVALID_SESSION":
            session_id = None
        history = history + [{"role": "assistant", "content": f"⚠️ {exc.user_message}"}]
        yield history, render_thought_html(""), gr.update(interactive=True), gr.update(interactive=True), session_id
        return

    # 把 Harness 組好的完整 payload（系統提示詞 + 歷史對話 + 這句清理過的
    # 提問）交給 LLMReasoning/ 模組，而不是只送清理後的使用者文字——這樣
    # 系統提示詞與歷史對話才會真的送進模型，不會被丟掉。LLMReasoning.process()
    # 內部會呼叫 LLM/ 模組取得回應、判定是否需要呼叫工具，並把這一輪的
    # 完整回覆寫回 Session 歷史，Frontend 不用再手動呼叫
    # Harness.append_assistant_message。
    history = history + [{"role": "assistant", "content": ""}]

    thought_acc = ""
    response_acc = ""

    for event, data in LLMReasoning.process(session_id, request_payload):
        if event == "thought_chunk":
            thought_acc += data
            # 串流中保持停用狀態
            yield history, render_thought_html(thought_acc), gr.update(interactive=False), gr.update(interactive=False), session_id

        elif event == "response_chunk":
            response_acc += data
            history[-1]["content"] = response_acc
            yield history, render_thought_html(thought_acc), gr.update(interactive=False), gr.update(interactive=False), session_id

        elif event == "end":
            history[-1]["content"] = response_acc
            # 串流結束，重新啟用輸入框與發送按鈕
            yield history, render_thought_html(thought_acc), gr.update(interactive=True), gr.update(interactive=True), session_id

def on_like(data: gr.LikeData):
    feedback = "讚" if data.liked else "踩"
    print(f"[feedback] index={data.index} value={feedback} message={data.value!r}")

def on_copy(data: gr.CopyData):
    print(f"[copy] value={data.value!r}")

# ----------------------------------------------------------------------------
# 建立 Gradio Blocks
# ----------------------------------------------------------------------------
def build_demo() -> gr.Blocks:
    with gr.Blocks(title="127.0.0.1:7860") as demo:
        # 每個瀏覽器分頁各自的 Harness Session ID（記憶體內，不落地儲存）。
        # 初始為 None；第一次呼叫 Harness.handle_turn() 時會自動產生 UUID v4。
        session_id_state = gr.State(value=None)

        # ================================================================
        # 主要對話頁
        # ================================================================
        with gr.Tab(label="對話"):
            with gr.Column(elem_id="app_header"):
                gr.Markdown("# AI 助手", elem_id="app_title")
                gr.Markdown("智慧對話、思考過程與回覆集中在同一個工作區。", elem_id="app_subtitle")

            with gr.Row(elem_id="main_layout"):
                # ---------------- 左側：固定 2/3 寬度 ----------------
                with gr.Column(elem_id="left_panel", scale=2, min_width=0):
                    chatbot = gr.Chatbot(
                        elem_id="chatbot_main",
                        buttons=["copy"],
                        feedback_options=("Like", "Dislike"),
                        like_user_message=False,
                    )

                    with gr.Group(elem_classes="input-group"):
                        with gr.Row():
                            msg_box = gr.Textbox(
                                placeholder="輸入訊息後按 Enter 或點擊發送…",
                                show_label=False,
                                autofocus=True,
                                container=False,
                                scale=8,
                            )
                            send_btn = gr.Button(
                                value="➤",
                                elem_id="send_btn",
                                scale=1,
                                min_width=52,
                            )

                    with gr.Row(elem_id="example-row"):
                        example_btns = [
                            gr.Button(q, size="sm") for q in EXAMPLE_QUESTIONS
                        ]

                # ---------------- 右側：固定 1/3 寬度 ----------------
                with gr.Column(elem_id="right_panel", scale=1, min_width=0):
                    thought_html = gr.HTML(
                        value=render_thought_html(""),
                        elem_id="thought_panel",
                        # 鎖死高度 = 一律填滿 #thought_panel（見 CUSTOM_CSS），
                        # 內容變長時交給 Gradio 自己的 overflow-y:auto 捲動；
                        # autoscroll=True 是 Gradio HTML 元件內建的「黏底」
                        # 行為：內容更新時若使用者本來就在底部附近，自動捲到
                        # 新內容；若使用者已經手動往上滑，就不會被拉回去。
                        # 這樣就不用自己刻一套 MutationObserver + 記錄捲動
                        # 位置的邏輯（原本刻的那套已經移除，見 HEAD_JS 說明）。
                        min_height="100%",
                        max_height="100%",
                        autoscroll=True,
                    )

        # ================================================================
        # 說明頁
        # ================================================================
        with gr.Tab(label="軌跡"):
            with gr.Column(elem_id="about_panel"):
                gr.Markdown(
                    """
                        待放架構圖
                    """
                )

        # ================================================================
        # 事件綁定
        # ================================================================
        msg_box.submit(
            fn=user_submit,
            inputs=[msg_box, chatbot],
            outputs=[chatbot, msg_box, thought_html],
        ).then(
            fn=disable_inputs,
            outputs=[msg_box, send_btn],
        ).then(
            fn=bot_response,
            inputs=[chatbot, session_id_state],
            outputs=[chatbot, thought_html, msg_box, send_btn, session_id_state],
        )

        send_btn.click(
            fn=user_submit,
            inputs=[msg_box, chatbot],
            outputs=[chatbot, msg_box, thought_html],
        ).then(
            fn=disable_inputs,
            outputs=[msg_box, send_btn],
        ).then(
            fn=bot_response,
            inputs=[chatbot, session_id_state],
            outputs=[chatbot, thought_html, msg_box, send_btn, session_id_state],
        )

        for btn, q in zip(example_btns, EXAMPLE_QUESTIONS):
            btn.click(
                fn=lambda question=q: question,
                outputs=[msg_box],
            ).then(
                fn=user_submit,
                inputs=[msg_box, chatbot],
                outputs=[chatbot, msg_box, thought_html],
            ).then(
                fn=disable_inputs,
                outputs=[msg_box, send_btn],
            ).then(
                fn=bot_response,
                inputs=[chatbot, session_id_state],
                outputs=[chatbot, thought_html, msg_box, send_btn, session_id_state],
            )

        chatbot.like(on_like, inputs=None, outputs=None)
        chatbot.copy(on_copy, inputs=None, outputs=None)

    return demo

demo = build_demo()

if __name__ == "__main__":
    demo.queue()
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        head=HEAD_JS,
        css=CUSTOM_CSS,
    )