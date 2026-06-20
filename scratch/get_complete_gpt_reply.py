import subprocess
import json
import time

wait_script = '''tell application "Google Chrome" to tell active tab of window 1 to execute javascript "
    var m = document.querySelectorAll('[data-message-author-role]');
    var count = m.length;
    var last = m[count-1];
    JSON.stringify({t: count, role: last ? last.getAttribute('data-message-author-role') : null, content: last ? last.textContent : ''});
"'''

last_len = -1
stable_count = 0

print("Polling for complete reply...")
for i in range(30):
    time.sleep(3)
    res = subprocess.run(['osascript', '-e', wait_script], capture_output=True, text=True)
    try:
        val = res.stdout.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1].replace('\\\\', '\\\\').replace('\\\"', '\"').replace('\\n', '\n')
            val = val.encode().decode('unicode_escape')
        data = json.loads(val)
        role = data.get('role')
        content = data.get('content', '')
        curr_len = len(content)
        
        # 排除包含正在思考或正在輸入等臨時狀態
        if role == 'assistant' and not content.strip().endswith('思考'):
            if curr_len == last_len and curr_len > 0:
                # 只有當內容包含 Owner Decision 或 [決定 1] 等完成特徵時才結束
                if "Owner Decision" in content or "[決定 1]" in content or "APPROVE_" in content:
                    stable_count += 1
                    if stable_count >= 2:
                        print("GPT stable! Full content retrieved.")
                        print("--- GPT REPLY CONTENT ---")
                        print(content)
                        print("-------------------------")
                        with open('.tmp/gpt_full_reply.txt', 'w', encoding='utf-8') as f:
                            f.write(content)
                        break
                else:
                    print(f"Waiting for key terms... current length={curr_len}")
                    stable_count = 0
            else:
                stable_count = 0
            last_len = curr_len
        else:
            stable_count = 0
            last_len = -1
    except Exception as e:
        pass
