import base64
import subprocess

# 讀取檔案
with open('.tmp/gpt_msg.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# base64
b64_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')

# applescript
script = f'''tell application "Google Chrome" to tell active tab of window 1 to execute javascript "var msg = decodeURIComponent(escape(window.atob('{b64_text}'))); var inp = document.querySelector('[role=textbox]'); inp.focus(); inp.textContent = msg; inp.dispatchEvent(new Event('input', {{ bubbles: true }})); 'text_set';"'''

subprocess.run(['osascript', '-e', script])
