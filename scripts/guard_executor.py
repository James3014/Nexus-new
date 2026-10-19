#!/usr/bin/env python3
import sys
import subprocess
import random
import os


def preview_argv_for_rm(cmd):
    """Map an ``rm`` argv to a read-only ``ls`` argv, or None if it is not one.

    Same rule as scripts/core/guard_executor.py (#2635).
    """
    if not cmd or os.path.basename(cmd[0]) != "rm":
        return None
    recursive = False
    operands = []
    end_of_options = False
    for arg in cmd[1:]:
        if not end_of_options and arg == "--":
            end_of_options = True
        elif not end_of_options and arg.startswith("--"):
            recursive = recursive or arg == "--recursive"
        elif not end_of_options and arg.startswith("-") and arg != "-":
            recursive = recursive or "r" in arg[1:].lower()
        else:
            operands.append(arg)
    return ["ls", "-ld" if recursive else "-l", "--", *operands]


def secure_execute():
    cmd = sys.argv[1:]
    if not cmd:
        sys.exit(0)
    cmd_str = " ".join(cmd)

    # 針對 rm 指令的攔截 (特別是危險參數)
    if "rm " in cmd_str and (
        "-r" in cmd_str or "-f" in cmd_str or "*" in cmd_str or "/" in cmd_str
    ):
        print("\n" + "=" * 60)
        print("🚨 [Guard_Executor] 觸發致命操作實體攔截！")
        print(f"嘗試執行的指令: {cmd_str}")
        print("=" * 60)

        # 1. 強制顯示影響範圍
        print("\n🔍 影響範圍預覽 (Dry Run):")
        # #2635: the preview is an ls argv built from the operands, never a
        # shell string (a file name such as "x; evil" would otherwise run).
        preview_argv = preview_argv_for_rm(cmd)
        try:
            if preview_argv is None:
                raise ValueError("not an rm argv")
            subprocess.run(preview_argv, check=False)
        except:
            print("  無法預覽影響範圍。")

        # 2. 強制需要人類輸入動態驗證碼 (無法被 AI 自動繞過)
        challenge = str(random.randint(1000, 9999))
        print("\n⚠️ 這是不可逆的操作。AI 無權執行。")
        print(
            f"👉 請 Sir 親自輸入驗證碼 [{challenge}] 以授權執行: ", end="", flush=True
        )

        try:
            # 讀取實體鍵盤輸入
            answer = input().strip()
            if answer != challenge:
                print("❌ 驗證失敗，操作已取消。")
                sys.exit(1)
        except Exception as e:
            print(f"❌ 無法獲取人類輸入，操作取消。({e})")
            sys.exit(1)

        print("✅ 實體授權通過，執行中...")

    # 執行原始指令
    try:
        # #2635: run the original argv; joining it into a shell string re-parsed
        # quoted operands.
        subprocess.run(list(cmd), check=True)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)


if __name__ == "__main__":
    secure_execute()
