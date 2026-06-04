import sys
import os

def fix_swe_script():
    path = 'benchmarking/swebench_lite/swe_local_heal.py'
    with open(path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    skip = False
    for i, line in enumerate(lines):
        if 'if res_ctx.solve_eligible:' in line:
            new_lines.append(line)
            new_lines.append('                    print("  ✅ SUCCESS: Solve eligible!")\n')
            new_lines.append('                    if res_ctx.final_patch:\n')
            new_lines.append('                        print("  --- Patch Preview ---")\n')
            new_lines.append('                        print("\\n".join(res_ctx.final_patch.splitlines()[:5]))\n')
            new_lines.append('                else:\n')
            new_lines.append('                    # 自動修補常見的 Repro 腳本缺失 (np, etc.)\n')
            new_lines.append('                    if not res_ctx.reproduced and "name \'np\' is not defined" in str(res_ctx.evaluation_report):\n')
            new_lines.append('                        print("  🔧 Auto-fixing repro script: Adding \'import numpy as np\'...")\n')
            new_lines.append('                        task["repro_script"] = "import numpy as np\\n" + task["repro_script"]\n')
            new_lines.append('                        res_ctx = pipeline.run(ctx)\n')
            new_lines.append('                        if res_ctx.final_patch:\n')
            new_lines.append('                            print("  --- Patch Preview ---")\n')
            new_lines.append('                            print("\\n".join(res_ctx.final_patch.splitlines()[:5]))\n')
            new_lines.append('                    else:\n')
            new_lines.append('                        print("  ✗ FAILED: Target remains unsolved.")\n')
            new_lines.append('                        if res_ctx.evaluation_report:\n')
            new_lines.append('                            print(f"  --- Evaluation Report ---\\n{res_ctx.evaluation_report}")\n')
            skip = True
        elif skip and 'row = build_result_row(task, res_ctx)' in line:
            new_lines.append('\n')
            new_lines.append(line)
            skip = False
        elif not skip:
            new_lines.append(line)
            
    with open(path, 'w') as f:
        f.writelines(new_lines)

if __name__ == '__main__':
    fix_swe_script()
