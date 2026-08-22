# -*- coding: utf-8 -*-
"""
Frontend/app.py
----------------
左右雙欄 AI 對話網站 (Gradio 實作，後端先用 fake_backend.py 假資料代替)

左側 (scale=2)：gr.Chatbot，顯示歷史問答。
    每則 AI 回覆下方固定顯示 📋複製 / 👍讚 / 👎踩 三個按鈕
    -> 使用 Gradio 6 Chatbot 原生的 `buttons=["copy"]` +
       `feedback_options=("Like","Dislike")`，穩定且不需要自行注入 DOM，
       點擊會自動變色 (Gradio 內建動畫)，也提供 `.like()` / `.copy()`
       事件掛勾，方便未來串接後端記錄回饋。

右側 (scale=1)：gr.HTML，即時串流顯示對應的思考鏈，並自動捲動到底部
    -> 用 MutationObserver 監看內容變化，隨串流自動 scrollTop = scrollHeight。
"""

import html
import gradio as gr

try:
    # 以 `python main.py` 執行時 (main.py 會把 Frontend 加進 sys.path)
    import fake_backend
except ImportError:  # pragma: no cover
    from Frontend import fake_backend


# ----------------------------------------------------------------------------
# 樣式 (CSS)
# ----------------------------------------------------------------------------
CUSTOM_CSS = """
.gradio-container {max-width: 1400px !important; margin: auto;}

#thought_panel {
    height: 620px;
    overflow: hidden;
    border: 1px solid var(--border-color-primary);
    border-radius: 12px;
    background: var(--background-fill-secondary);
    padding: 0;
}
.thought-scroll-inner {
    height: 100%;
    overflow-y: auto;
    padding: 16px;
    box-sizing: border-box;
    font-size: 14px;
    line-height: 1.7;
}
.thought-empty {
    color: var(--body-text-color-subdued);
    font-style: italic;
}

#chatbot_main {height: 560px;}

#example-row {margin-top: 4px;}
#example-row button {white-space: normal;}
"""


# ----------------------------------------------------------------------------
# 前端 JavaScript：讓右側思考鏈區塊在內容更新時自動捲動到最底部
# 透過 launch(head=...) 注入到 <head>
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
        inner = '<span class="thought-empty">尚無思考內容…</span>'
    else:
        inner = html.escape(thought_text).replace("\n", "<br>")
    return f'<div class="thought-scroll-inner">{inner}</div>'


def _extract_text(content) -> str:
    """Chatbot 訊息的 content 送到後端事件時，可能是純字串，
    也可能被 Gradio 轉成 [{'type': 'text', 'text': '...'}] 這種多模態格式，
    這裡統一轉成純文字，避免 .lower() / f-string 等操作出錯。"""
    if isinstance(content, str):
        return content
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
    """使用者送出訊息：立刻顯示在左側對話區，並清空輸入框、右側思考區"""
    user_message = (user_message or "").strip()
    if not user_message:
        return history, "", render_thought_html("")

    history = history + [{"role": "user", "content": user_message}]
    return history, "", render_thought_html("")


def disable_input():
    return gr.update(interactive=False)


def bot_response(history):
    """依據最後一則使用者訊息，串流產生思考鏈 (右) + 最終回覆 (左)"""
    if not history or history[-1]["role"] != "user":
        yield history, render_thought_html(""), gr.update(interactive=True)
        return

    user_message = _extract_text(history[-1]["content"])
    history = history + [{"role": "assistant", "content": ""}]

    thought_acc = ""
    response_acc = ""

    for event, data in fake_backend.stream_answer(user_message):
        if event == "thought_chunk":
            thought_acc += data
            yield history, render_thought_html(thought_acc), gr.update(interactive=False)

        elif event == "response_chunk":
            response_acc += data
            history[-1]["content"] = response_acc
            yield history, render_thought_html(thought_acc), gr.update(interactive=False)

        elif event == "end":
            history[-1]["content"] = response_acc
            # 串流結束 -> 重新啟用輸入框；此時 Gradio 會在該則訊息下方
            # 顯示 📋複製 / 👍 / 👎 按鈕 (buttons / feedback_options 設定)
            yield history, render_thought_html(thought_acc), gr.update(interactive=True)


def on_like(data: gr.LikeData):
    """使用者點擊 👍 / 👎 時觸發 (Gradio 內建按鈕已自動處理變色動畫)。
    這裡先用 print 模擬記錄，之後可換成呼叫真正後端 API。"""
    feedback = "讚" if data.liked else "踩"
    print(f"[feedback] index={data.index} value={feedback} message={data.value!r}")


def on_copy(data: gr.CopyData):
    """使用者點擊 📋 複製按鈕時觸發（複製到剪貼簿已由 Gradio 前端內建處理）"""
    print(f"[copy] value={data.value!r}")


# ----------------------------------------------------------------------------
# 建立 Gradio Blocks
# ----------------------------------------------------------------------------
def build_demo() -> gr.Blocks:
    with gr.Blocks(title="AI 雙欄對話 Demo") as demo:
        gr.Markdown("## 🤖 AI 對話助手（左：對話紀錄　右：思考鏈，後端目前為假資料）")

        with gr.Row():
            # ---------------- 左側：對話區 scale=2 (~66%) ----------------
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(
                    elem_id="chatbot_main",
                    label="對話紀錄",
                    height=560,
                    buttons=["copy"],                       # 每則訊息下方顯示 📋 複製
                    feedback_options=("Like", "Dislike"),    # 每則 AI 訊息顯示 👍 / 👎
                    like_user_message=False,
                )

                msg_box = gr.Textbox(
                    placeholder="輸入訊息後按 Enter 送出…",
                    show_label=False,
                    autofocus=True,
                )

                with gr.Row(elem_id="example-row"):
                    example_btns = [
                        gr.Button(q, size="sm", variant="secondary")
                        for q in EXAMPLE_QUESTIONS
                    ]

            # ---------------- 右側：思考鏈區 scale=1 (~34%) ----------------
            with gr.Column(scale=1):
                gr.Markdown("### 🧠 思考鏈 (Chain of Thought)")
                thought_html = gr.HTML(
                    value=render_thought_html(""),
                    elem_id="thought_panel",
                )

        # ---------------- 事件綁定 ----------------
        # 1) 使用者送出訊息 -> 立即顯示於左側 + 清空思考區
        # 2) 停用輸入框，避免串流過程中重複送出
        # 3) 呼叫 bot_response 逐字串流輸出思考鏈 + 最終回覆，結束後重新啟用輸入框
        msg_box.submit(
            fn=user_submit,
            inputs=[msg_box, chatbot],
            outputs=[chatbot, msg_box, thought_html],
        ).then(
            fn=disable_input,
            outputs=[msg_box],
        ).then(
            fn=bot_response,
            inputs=[chatbot],
            outputs=[chatbot, thought_html, msg_box],
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
                fn=disable_input,
                outputs=[msg_box],
            ).then(
                fn=bot_response,
                inputs=[chatbot],
                outputs=[chatbot, thought_html, msg_box],
            )

        # 按鈕點擊回饋（讚 / 踩 / 複製）事件掛勾，未來可接後端 API 記錄
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