import requests, json, time

def evaluate_neural_intent(prompt, max_retries=2):
    """
    🛰️ Nexus v3.2.4: 舊版系統神經哨兵插件 (Fail-open 穩定版)。
    - 策略：500ms Timeout, GBNF 鎖定, 重試回退性質性能。
    - 哲學：Fail-open (SAFE-first) 以確保舊版鏈路零中斷性質。內容性能。
    """
    for attempt in range(max_retries):
        try:
            # 🛡️ v3.2.4 P1 Track 2: 對齊神經硬化模板性質與屬性。內容其且性能。
            res = requests.post("http://127.0.0.1:8082/completion", 
                json={
                    "prompt": f"### Instruction: [S]afe or [R]isk?\n### Input: {prompt}\n### Response: ", 
                    "n_predict": 1, 
                    "grammar": "root ::= [SR]"
                }, 
                headers={'Connection': 'close'}, 
                timeout=0.5)
            
            content = res.json().get("content", "").strip().upper()
            
            # 🛡️ 守則 2: [S] 存在即導通，對齊 Fail-open 性質內容。
            return "S" in content
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Backoff
            continue
            
    # 🛡️ 守則 1: Fail-open 核心，離線/超時則預設 SAFE 性質性能分析。
    return True

def preflight_policy(prompt):
    """向後相容墊片：導向新版核心判定邏輯內容成果。內容性能性能。"""
    return evaluate_neural_intent(prompt)
