# -*- coding: utf-8 -*-
"""
Frontend/app.py
----------------
左右雙欄 AI 對話網站 (Gradio 實作，後端先用 fake_backend.py 假資料代替)
"""

import html
import gradio as gr

try:
    import fake_backend
except ImportError:  # pragma: no cover
    from Frontend import fake_backend


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
    margin: 0 !important;
}

#main_layout > .gr-column {
    min-width: 0 !important;
    width: auto !important;
    height: 100% !important;
    min-height: 0 !important;
    display: flex !important;
    flex-direction: column !important;
}

#left_panel,
#right_panel {
    min-width: 0 !important;
    min-height: 0 !important;
    height: 100% !important;
    box-sizing: border-box !important;
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
    min-height: 0 !important;
    height: auto !important;
    width: 100% !important;
    border-radius: 16px !important;
    border: 1px solid var(--border-color-primary) !important;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.055) !important;
    overflow: hidden !important;
    background: var(--background-fill-primary) !important;
}

#chatbot_main .message {
    line-height: 1.7 !important;
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
    width: 100%;
    height: 100%;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 22px;
    box-sizing: border-box;
    font-size: 14px;
    line-height: 1.75;
    font-family: 'Cascadia Mono', 'SFMono-Regular', Consolas, monospace;
    white-space: normal;
    word-break: break-word;
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
HEAD_JS = """
<script>
(function watchThoughtPanel() {
    const trySetup = () => {
        const panel = document.getElementById('thought_panel');
        if (!panel) {
            setTimeout(trySetup, 300);
            return;
        }
        const scrollToBottom = () => {
            const inner = panel.querySelector('.thought-scroll-inner');
            if (inner) inner.scrollTop = inner.scrollHeight;
        };
        const observer = new MutationObserver(scrollToBottom);
        observer.observe(panel, {childList: true, subtree: true, characterData: true});
        scrollToBottom();
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', trySetup);
    } else {
        trySetup();
    }
})();
</script>
"""

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

def bot_response(history):
    if not history or history[-1]["role"] != "user":
        # 如果無效，立刻重新啟用輸入元件
        yield history, render_thought_html(""), gr.update(interactive=True), gr.update(interactive=True)
        return

    user_message = _extract_text(history[-1]["content"])
    history = history + [{"role": "assistant", "content": ""}]

    thought_acc = ""
    response_acc = ""

    for event, data in fake_backend.stream_answer(user_message):
        if event == "thought_chunk":
            thought_acc += data
            # 串流中保持停用狀態
            yield history, render_thought_html(thought_acc), gr.update(interactive=False), gr.update(interactive=False)

        elif event == "response_chunk":
            response_acc += data
            history[-1]["content"] = response_acc
            yield history, render_thought_html(thought_acc), gr.update(interactive=False), gr.update(interactive=False)

        elif event == "end":
            history[-1]["content"] = response_acc
            # 串流結束，重新啟用輸入框與發送按鈕
            yield history, render_thought_html(thought_acc), gr.update(interactive=True), gr.update(interactive=True)

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
                    )

        # ================================================================
        # 說明頁
        # ================================================================
        with gr.Tab(label="軌跡"):
            with gr.Column(elem_id="about_panel"):
                gr.Markdown(
                    """# AI 助手 2.0

"
                    "- 使用者可以透過輸入框與 AI 互動。
"
                    "- AI 回覆會即時串流顯示。
"
                    "- 右側面板用於顯示思考過程。
"
                    "- 可直接按 Enter 或點擊發送按鈕送出訊息。
"
                    "- 下方提供常用問題範例，可快速開始對話。"""
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
            inputs=[chatbot],
            outputs=[chatbot, thought_html, msg_box, send_btn],
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
            inputs=[chatbot],
            outputs=[chatbot, thought_html, msg_box, send_btn],
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
                inputs=[chatbot],
                outputs=[chatbot, thought_html, msg_box, send_btn],
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