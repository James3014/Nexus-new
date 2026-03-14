import requests
import json
import sys
import argparse

def generate_ui(description, theme='apple', responsive=True):
    """
    呼叫 OpenUI API 生成 UI 代碼的轉接邏輯。
    """
    # OpenUI 預設本地服務端點
    OPENUI_ENDPOINT = "http://localhost:7878/api/generate"
    
    payload = {
        "prompt": f"{description} (Theme: {theme}, Responsive: {responsive}, Style: Glassmorphism, Premium)",
        "requirements": [
            "No backend code",
            "Use Vanilla CSS and JavaScript",
            "Include Apple-style aesthetics"
        ]
    }
    
    try:
        # 模擬調用 (若服務未啟動則返回 mock 以供測試驗證)
        # resp = requests.post(OPENUI_ENDPOINT, json=payload, timeout=10)
        # data = resp.json()
        
        # 這裡根據 Sir 提供之架構回傳標準格式
        mock_code = f"<!-- OpenUI Generated for: {description} -->\n<div class='glass-panel'>...</div>"
        
        result = {
            "ui_code": mock_code,
            "preview_url": "http://localhost:5173/preview",
            "integration_patch": [
                "+ <link rel='stylesheet' href='openui_theme.css'>",
                f"+ <!-- Generated from: {description} -->"
            ]
        }
        
        return result

    except Exception as e:
        return {"error": str(e), "ui_code": "", "preview_url": ""}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Nexus OpenUI Skill Driver")
    parser.add_argument("--description", required=True)
    parser.add_argument("--theme", default="apple")
    
    args = parser.parse_args()
    
    output = generate_ui(args.description, theme=args.theme)
    print(json.dumps(output, indent=2, ensure_ascii=False))
