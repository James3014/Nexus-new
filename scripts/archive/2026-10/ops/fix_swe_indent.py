import sys

def fix_indent():
    path = 'benchmarking/swebench_lite/swe_local_heal.py'
    with open(path, 'r') as f:
        content = f.read()
    
    # 尋找錯誤的區塊並取代為正確縮進的區塊
    old_block = """                if not res_ctx.reproduced and "name 'np' is not defined" in str(res_ctx.evaluation_report):
                    print("  🔧 Auto-fixing repro script: Adding 'import numpy as np'...")
                    task["repro_script"] = "import numpy as np\\n" + task["repro_script"]
                    # 重新執行一次
                    res_ctx = pipeline.run(ctx)
                    if res_ctx.final_patch:
                        print("  --- Patch Preview ---")
                        print("\\n".join(res_ctx.final_patch.splitlines()[:5]))"""
    
    # 實際在檔案中可能因為縮進混亂而不完全匹配
    # 改用更寬鬆的搜尋取代
    
    # 我們重新寫入這一區段
    marker = 'res_ctx.token_telemetry_status = "estimated"'
    if marker in content:
        parts = content.split(marker)
        # 在第一個估計標記後注入邏輯 (位於 else 分支末尾)
        head = parts[0] + marker + '\n'
        tail = parts[1]
        
        # 尋找下一個 if res_ctx.solve_eligible
        if 'if res_ctx.solve_eligible:' in tail:
            subparts = tail.split('if res_ctx.solve_eligible:')
            injection = """
                if not res_ctx.reproduced and "name 'np' is not defined" in str(res_ctx.evaluation_report):
                    print("  🔧 Auto-fixing repro script: Adding 'import numpy as np'...")
                    task["repro_script"] = "import numpy as np\\n" + task["repro_script"]
                    res_ctx = pipeline.run(ctx)
"""
            content = head + subparts[0] + injection + '                if res_ctx.solve_eligible:' + subparts[1]
            
            with open(path, 'w') as f:
                f.write(content)
            print("Successfully fixed indentation in swe_local_heal.py")
        else:
            print("Could not find solve_eligible marker")
    else:
        print("Could not find estimated marker")

if __name__ == '__main__':
    fix_indent()
