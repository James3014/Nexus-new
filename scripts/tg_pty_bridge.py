import os
import re
import requests
import time
import trafilatura
import subprocess
import threading
from datetime import datetime

# API 設定
TOKEN = "8765227805:AAFPf3gT12NhgT7i5xdZIa2S3DeV1dEwdZg"
API_URL = f"https://api.telegram.org/bot{TOKEN}"
INBOX_DIR = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/Inbox"
JINA_KEY = "jina_ecccac068fdf49fc8d7e986af7f0436dmd-mudbl_v3lZRWbBoN3kSwi75ze"


def send_to_tg(chat_id, text):
    if not text:
        return
    if len(text) > 4000:
        text = text[:4000] + "..."
    requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})


def fetch_content_strong(url):
    """
    強勢抓取：L1 Trafilatura -> L2 Jina Reader
    """
    # L1: 快速抓取
    try:
        downloaded = trafilatura.fetch_url(url)
        content = trafilatura.extract(downloaded)
        if content and len(content) > 200:
            return content
    except:
        pass

    # L2: Jina 破防抓取 (特別針對 FB, LinkedIn 等)
    try:
        headers = {"Authorization": f"Bearer {JINA_KEY}", "X-Return-Format": "markdown"}
        resp = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
    except:
        pass

    return None


def ask_gemini_worker(chat_id, prompt, is_url=False):
    try:
        res = subprocess.run(
            ["gemini", "-m", "gemini-3-flash-preview", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            cwd="/Users/jameschen/Downloads/obsidian/知識庫",
        )
        output = (res.stdout + res.stderr).strip()
        # 移除噪音
        output = re.sub(
            r"--- /.*? ---.*?Sir，大腦內容已同步完畢。", "", output, flags=re.DOTALL
        )
        lines = output.split("\n")
        clean_lines = [
            l
            for l in lines
            if not any(
                x in l
                for x in [
                    "Warning:",
                    "Error executing",
                    "Loaded cached",
                    "Loading extension",
                    "Server",
                ]
            )
        ]
        final_text = "\n".join(clean_lines).strip()

        if final_text:
            # 1. 發送到 Telegram
            prefix = "✅ **[大腦結晶完成]**\n\n" if is_url else ""
            send_to_tg(chat_id, f"{prefix}{final_text}")

            # 2. 同時實體歸檔到大腦 Inbox (Sir 指定位置)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = os.path.join(INBOX_DIR, f"TG_CRYSTAL_{ts}.md")
            with open(archive_path, "w") as f:
                f.write(f"# 📡 Telegram 大腦分析: {ts}\n\n{final_text}")
            print(f"📂 [Archive] 已同步至 Inbox: {archive_path}")
        else:
            send_to_tg(chat_id, "❌ 大腦回傳解析失敗。")
    except Exception as e:
        send_to_tg(chat_id, f"❌ 大腦異常: {str(e)}")


def handle_message(chat_id, text):
    urls = re.findall(r"(https?://\S+)", text)
    if urls:
        url = urls[0]
        send_to_tg(chat_id, "📡 正在執行『強勢偵查協定』：正在破防爬取網頁...")
        content = fetch_content_strong(url)

        if content:
            send_to_tg(chat_id, "🧠 內容已讀取，大腦正在對位分析中...")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs(INBOX_DIR, exist_ok=True)
            with open(os.path.join(INBOX_DIR, f"TG_RECV_{ts}.md"), "w") as f:
                f.write(f"# Telegram Recv: {url}\n\n{content}")

            system_instr = "你是一個 Lvl 15 戰略分析官。請對以下內容產出 TREE 結晶 (Trunk + Items)，並加入『🕸️ 語義聯結』。僅輸出 Markdown。"
            threading.Thread(
                target=ask_gemini_worker,
                args=(chat_id, f"{system_instr}\n\n網頁內容：\n{content[:8000]}", True),
            ).start()
        else:
            send_to_tg(
                chat_id,
                "❌ 即使啟動破防協定也無法讀取該網址，請確認連結有效性或手動貼上文字。",
            )
    else:
        send_to_tg(chat_id, "💭 正在思考回覆...")
        threading.Thread(target=ask_gemini_worker, args=(chat_id, text, False)).start()


def poll():
    last_update_id = None
    print("🚀 Muse-Core Telegram Soul (V14 - 全能破防版) 啟動。")
    while True:
        try:
            req_url = f"{API_URL}/getUpdates?timeout=15&offset={last_update_id + 1 if last_update_id else ''}"
            resp = requests.get(req_url).json()
            if resp.get("ok"):
                for update in resp["result"]:
                    last_update_id = update["update_id"]
                    msg = update.get("message", {})
                    chat_id = msg.get("chat", {}).get("id")
                    text = msg.get("text", "")
                    if chat_id and text:
                        if text == "/start":
                            send_to_tg(
                                chat_id,
                                "🤖 Sir, 移動戰術大腦已對位。具備強勢抓取能力。",
                            )
                            continue
                        handle_message(chat_id, text)
        except Exception:
            time.sleep(2)
        time.sleep(1)


if __name__ == "__main__":
    poll()
