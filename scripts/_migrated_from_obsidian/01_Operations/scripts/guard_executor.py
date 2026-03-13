import subprocess
import sys
import os
import pty

NOTIFY_SCRIPT = "/Users/jameschen/.openclaw/skills/audio-notify/scripts/notify.py"

def run_with_pty_guard(command):
    print(f"🛡️ Guard Executor (PTY Mode): Monitoring [{command}]...")
    
    # 使用 PTY 模擬互動式終端，防止輸出被緩衝
    master, slave = pty.openpty()
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=slave,
        stderr=slave,
        stdin=slave,
        text=True
    )
    os.close(slave)

    buffer = ""
    while True:
        try:
            # 逐字讀取 master 輸出
            char = os.read(master, 1).decode("utf-8", errors="ignore")
            if not char: break
            sys.stdout.write(char)
            sys.stdout.flush()
            buffer += char
            
            # 如果緩衝區太大，截斷
            if len(buffer) > 500: buffer = buffer[-500:]
            
            # 關鍵字攔截：包含特殊符號 ●
            if any(k in buffer for k in ["Allow once", "Allow for this session", "●"]):
                print("\n🚨 [ALERT] Permission prompt detected!")
                os.system(f"python3 {NOTIFY_SCRIPT} '請審核行動'")
                buffer = "" # 觸發後清空，避免重複報警
        except EOFError:
            break
        except Exception:
            break
            
    return_code = process.wait()
    return return_code

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 guard_executor.py \"command\"")
    else:
        run_with_pty_guard(" ".join(sys.argv[1:]))
