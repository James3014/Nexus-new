#!/usr/bin/env python3
import time
import sys
import argparse

def ollama_generate(system_prompt, user_prompt, **kwargs):
    # 針對不同的 Phase 回傳適當內容
    if "Plan" in system_prompt or "PLAN" in system_prompt:
        return "r:0,d:0,p:1,c:0"
        
    if "Repair" in system_prompt or "REPAIR" in system_prompt:
        # 模擬產生 SEARCH/REPLACE 補丁
        # 這裡我們需要知道目標檔案名，模擬從 user_prompt 提取
        file_name = "reproduce_bug.py"
        if "reproduce_bug.py" in user_prompt:
            file_name = "reproduce_bug.py"
        
        # 隨機產生不同的補丁以模擬委員會候選
        import random
        v = random.randint(1, 100)
        
        return f"""
<<<<<<< SEARCH
# Initial content
=======
# Fixed content v{v}
import numpy as np
>>>>>>> REPLACE
"""

    if "Verify" in system_prompt or "VERIFY" in system_prompt:
        return "r:0,d:0,p:4,c:0"
        
    return "r:0,d:0,p:0,c:0"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-m")
    parser.add_argument("-y", action="store_true")
    parser.add_argument("--output-format")
    parser.add_argument("-p")
    args = parser.parse_args()

    if args.p and "sleep" in args.p:
        time.sleep(10)
        print("Slept 10 seconds")
    else:
        print("OK")

if __name__ == "__main__":
    main()
