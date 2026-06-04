import sys

def fix_denoiser():
    path = 'nexus/services/local_heal/env_denoiser.py'
    with open(path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.strip() == '...':
            continue
        new_lines.append(line)
        
    with open(path, 'w') as f:
        f.writelines(new_lines)
    print("Fixed env_denoiser.py")

if __name__ == '__main__':
    fix_denoiser()
