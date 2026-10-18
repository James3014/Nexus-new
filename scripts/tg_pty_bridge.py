import os
import re
import requests
import time
import trafilatura
import subprocess
import threading
from datetime import datetime

# 🛡️ Nexus Integration
try:
    from nexus.services.gateway import BattlesuitGateway as LLMClient
except ImportError:
    LLMClient = None

# API 設定
# SEC-001: credentials come from the environment; the old literals were public and must be revoked.
TOKEN = os.environ.get("NEXUS_TG_BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("NEXUS_TG_BOT_TOKEN is not set")
API_URL = f"https://api.telegram.org/bot{TOKEN}"
INBOX_DIR = "/Users/jameschen/Downloads/obsidian/知識庫/01_Operations/Inbox"
JINA_KEY = os.environ.get("JINA_API_KEY", "")


def send_to_tg(chat_id, text):
    if not text:
        return
    if len(text) > 4000:
        text = text[:4000] + "..."
    requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})


def fetch_content_strong(url):
    """強勢抓取：L1 Trafilatura -> L2 Jina Reader"""
    try:
        downloaded = trafilatura.fetch_url(url)
        content = trafilatura.extract(downloaded)
        if content and len(content) > 200:
            return content
    except:
        pass
    try:
        headers = {"X-Return-Format": "markdown"}
        if JINA_KEY:
            headers["Authorization"] = f"Bearer {JINA_KEY}"
        resp = requests.get(f"https://r.jina.ai/{url}", headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
    except:
        pass
    return None


def process_output(chat_id, final_text, is_url):
    if final_text:
        # 1. 發送到 Telegram
        prefix = "✅ **[大腦結晶完成]**\n\n" if is_url else ""
        send_to_tg(chat_id, f"{prefix}{final_text}")

        # 2. 同時實體歸檔到大腦 Inbox
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = os.path.join(INBOX_DIR, f"TG_CRYSTAL_{ts}.md")
        os.makedirs(INBOX_DIR, exist_ok=True)
        with open(archive_path, "w") as f:
            f.write(f"# 📡 Telegram 大腦分析: {ts}\n\n{final_text}")
        print(f"📂 [Archive] 已同步至 Inbox: {archive_path}")
    else:
        send_to_tg(chat_id, "❌ 大腦回傳解析失敗。")


def ask_gemini_worker(chat_id, prompt, is_url=False):
    # 🛡️ Nexus Battlesuit Gateway Integration
    if LLMClient:
        try:
            client = LLMClient(project_root="/Users/jameschen/Downloads/obsidian/知識庫")
            data, final_text = client.ask(prompt, "", phase="X")
            if data.get("status") != "FAIL":
                process_output(chat_id, final_text, is_url)
                return
        except Exception as e:
            print(f"⚠️ Gateway Error: {e}")

    try:
        res = subprocess.run(
            ["gemini", "-m", "gemini-3-flash-preview", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=180,
            cwd="/Users/jameschen/Downloads/obsidian/知識庫",
        )
        output = (res.stdout + res.stderr).strip()
        output = re.sub(r"--- /.*? ---.*?Sir，大腦內容已同步完畢。", "", output, flags=re.DOTALL)
        
        lines = output.split("\n")
        clean_lines = [l for l in lines if not any(x in l for x in ["Warning:", "Error executing", "Loaded cached", "Loading extension", "Server"])]
        final_text = "\n".join(clean_lines).strip()
        process_output(chat_id, final_text, is_url)
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
            send_to_tg(chat_id, "❌ 即使啟動破防協定也無法讀取該網址，請確認連結有效性或手動貼上文字。")
    else:
        send_to_tg(chat_id, "💭 正在思考回覆...")
        threading.Thread(target=ask_gemini_worker, args=(chat_id, text, False)).start()


# SEC-004: only these Telegram user ids (the sender, not the chat) may drive the
# bridge. Comma-separated; malformed entries are ignored, empty means nobody.
ALLOWED_USER_IDS = set()
for _raw in os.environ.get("NEXUS_TG_ALLOWED_USER_IDS", "").split(","):
    try:
        ALLOWED_USER_IDS.add(int(_raw.strip()))
    except ValueError:
        pass


def poll():
    last_update_id = None
    print("🚀 Muse-Core Telegram Soul (V16 - Battlesuit Powered) 啟動。")
    if not ALLOWED_USER_IDS:
        print("⚠️ NEXUS_TG_ALLOWED_USER_IDS is empty: every message will be ignored.")
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
                    if msg.get("from", {}).get("id") not in ALLOWED_USER_IDS:
                        continue
                    if chat_id and text:
                        if text == "/start":
                            send_to_tg(chat_id, "🤖 Sir, 移動戰術大腦已對位。具備戰備閘道通訊能力。")
                            continue
                        handle_message(chat_id, text)
        except Exception:
            time.sleep(2)
        time.sleep(1)


if __name__ == "__main__":
    poll()
