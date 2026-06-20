import subprocess
import base64
import json
import time

# 讀取檔案
with open('.tmp/gpt_msg.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# base64
b64_text = base64.b64encode(text.encode('utf-8')).decode('utf-8')

# 1. 輸入文字
set_script = f'''tell application "Google Chrome" to tell active tab of window 1 to execute javascript "var msg = decodeURIComponent(escape(window.atob('{b64_text}'))); var inp = document.querySelector('[role=textbox]'); inp.focus(); inp.textContent = msg; inp.dispatchEvent(new Event('input', {{ bubbles: true }})); 'text_set';"'''
subprocess.run(['osascript', '-e', set_script])

# 2. 點擊傳送
click_script = '''tell application "Google Chrome" to tell active tab of window 1 to execute javascript "
    var btn = document.querySelector('[data-testid=\\"send-button\\"]') || 
              document.querySelector('[aria-label*=\\"Send\\"]') || 
              document.querySelector('[aria-label*=\\"傳送\\"]');
    if (btn) {
        btn.click();
        'clicked';
    } else {
        var btns = document.querySelectorAll('button');
        var clicked = false;
        for (var i = btns.length - 1; i >= 0; i--) {
            var label = btns[i].getAttribute('aria-label') || '';
            if (label.indexOf('Send') >= 0 || label.indexOf('傳送') >= 0) {
                btns[i].click();
                clicked = true;
                break;
            }
        }
        clicked ? 'clicked_fallback' : 'btn_not_found';
    }
"'''
time.sleep(1)
subprocess.run(['osascript', '-e', click_script])

# 3. 等待並讀取完整 GPT 回覆
wait_script = '''tell application "Google Chrome" to tell active tab of window 1 to execute javascript "
    var m = document.querySelectorAll('[data-message-author-role]');
    var count = m.length;
    var last = m[count-1];
    JSON.stringify({t: count, role: last ? last.getAttribute('data-message-author-role') : null, content: last ? last.textContent : ''});
"'''

print("Waiting for ChatGPT to reply...")
for i in range(12):
    time.sleep(10)
    res = subprocess.run(['osascript', '-e', wait_script], capture_output=True, text=True)
    try:
        val = res.stdout.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\\\', '\\\\').replace('\\\"', '\"').replace('\\n', '\n')
            val = val.encode().decode('unicode_escape')
        data = json.loads(val)
        role = data.get('role')
        if role == 'assistant':
            print("GPT replied successfully!")
            print("--- GPT REPLY CONTENT ---")
            print(data.get('content'))
            print("-------------------------")
            break
    except Exception as e:
        print("Error parsing response:", e)
