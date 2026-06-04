import sys

def fix_denoiser_final():
    path = 'nexus/services/local_heal/env_denoiser.py'
    with open(path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    in_wrong_method = False
    
    # 1. 提取 _ensure_astropy_dependencies 方法
    ensure_method = [
        "    def _ensure_astropy_dependencies(self):\n",
        "        \"\"\"物理補齊 Astropy 編譯所需的基礎套件\"\"\"\n",
        "        deps = [\"numpy\", \"pyerfa\", \"extension-helpers\", \"cython\"]\n",
        "        has_uv = bool(shutil.which(\"uv\"))\n",
        "        for dep in deps:\n",
        "            try:\n",
        "                if has_uv:\n",
        "                    self.run_command([\"uv\", \"pip\", \"install\", dep, \"--python\", self.python_executable], self.repo_dir, 60)\n",
        "                else:\n",
        "                    self.run_command([self.python_executable, \"-m\", \"pip\", \"install\", dep], self.repo_dir, 60)\n",
        "            except:\n",
        "                pass\n"
    ]

    # 2. 重構檔案內容
    skip_source = False
    for line in lines:
        if 'def _ensure_astropy_dependencies(self):' in line:
            skip_source = True
            continue
        if skip_source:
            if 'pass' in line and 'except:' in lines[lines.index(line)-1]:
                skip_source = False
                continue
            continue
        new_lines.append(line)
        
    # 3. 確保 prepare_from_evidence 邏輯連貫
    content = "".join(new_lines)
    # 移除多餘的重複定義（如果有的話）
    
    # 4. 把方法放到類別末尾
    if 'return EnvDenoiseResult()' in content:
        parts = content.split('return EnvDenoiseResult()')
        final_content = parts[0] + 'return EnvDenoiseResult()\n\n' + "".join(ensure_method) + parts[1]
        with open(path, 'w') as f:
            f.write(final_content)
        print("Successfully restructured env_denoiser.py")
    else:
        print("Could not find end of prepare_from_evidence")

if __name__ == '__main__':
    fix_denoiser_final()
