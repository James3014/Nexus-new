#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "google-genai",
#     "pyperclip",
#     "httpx",
#     "beautifulsoup4",
#     "rich",
# ]
# ///

import os
import sys
import argparse
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
import pyperclip
from google import genai
from google.genai import types
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

console = Console()

# ---------------------------------------------------------------------------
# 1. 讀取模組 (Input Sources)
# ---------------------------------------------------------------------------

def is_url(string):
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def fetch_url_text(url):
    console.print(f"[dim]正在抓取網頁內容: {url}[/dim]")
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            # 移除不必要的標籤
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.extract()
            text = soup.get_text(separator="\n")
            # 簡單清理空白
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text
    except Exception as e:
        console.print(f"[red]抓取網頁失敗: {e}[/red]")
        sys.exit(1)

def read_file_text(filepath):
    console.print(f"[dim]正在讀取本地檔案: {filepath}[/dim]")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        console.print(f"[red]讀取檔案失敗: {e}[/red]")
        sys.exit(1)

def get_input_text(source=None):
    if source:
        if is_url(source):
            return fetch_url_text(source)
        elif os.path.isfile(source):
            return read_file_text(source)
        else:
            return source # 當作純文字處理
    else:
        # 預設讀取剪貼簿
        console.print("[dim]未提供來源，正在讀取剪貼簿內容...[/dim]")
        text = pyperclip.paste()
        if not text:
            console.print("[red]剪貼簿是空的！[/red]")
            sys.exit(1)
        return text

# ---------------------------------------------------------------------------
# 2. 大腦調用模組 (LLM Engine)
# ---------------------------------------------------------------------------

def ask_llm(prompt, text, role, model_name="gemini-2.5-pro"):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]錯誤: 找不到 GEMINI_API_KEY 環境變數。請在環境中設定它。[/red]")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    full_prompt = f"{role}\n\n任務指令：\n{prompt}\n\n=== 輸入內容 ===\n{text}\n=== 輸入結束 ==="
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
            ),
        )
        return response.text
    except Exception as e:
        console.print(f"[red]LLM 生成失敗: {e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# 3. Agentic Loops Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(source_text):
    console.print(Panel(f"原文長度: {len(source_text)} 字", title="📥 輸入確認", border_style="blue"))
    
    # [代理 A] 摘要提取器 (Analytical Agent)
    console.print("[yellow]🤖 代理 A (分析師) 正在萃取核心樹幹...[/yellow]")
    agent_a_role = "你是一個頂尖的資訊架構師，擅長從龐雜的資訊中提取出最核心的結構與樹幹 (Trunk)。"
    agent_a_prompt = "請從以下文本中提取最重要的 3-5 個核心觀點。去除所有冗言贅字，輸出純粹且極度精煉的條列式重點。這些重點必須是具有高度洞察力的結論，而非表面描述。"
    trunk_text = ask_llm(agent_a_prompt, source_text, agent_a_role, "gemini-2.5-flash")
    console.print(Panel(Markdown(trunk_text), title="🌲 核心樹幹 (Trunk)", border_style="green"))
    
    # [代理 B] Threads 金牌寫手 (Hook Agent)
    console.print("[yellow]🤖 代理 B (行銷寫手) 正在轉化 Threads 文案...[/yellow]")
    agent_b_role = "你是一個千萬流量的 Threads 操盤手，洞悉人性，擅長將硬核知識轉化為極具破壞力的短文案。"
    agent_b_prompt = "請根據上述的「核心樹幹」，寫出一篇 Threads 短文案（約 200-300 字）。\n要求：\n1. 第一句話必須是極具痛點、反直覺或能瞬間抓住眼球的 Hook。\n2. 資訊密度極高，絕對不說廢話、不說教。\n3. 適當使用幾個 Emoji 點綴，版面要俐落。\n4. 結尾要帶有啟發性，或是引發讀者思考的一句話。"
    threads_copy = ask_llm(agent_b_prompt, trunk_text, agent_b_role, "gemini-2.5-pro")
    console.print(Panel(Markdown(threads_copy), title="🧵 Threads 短文案", border_style="magenta"))
    
    # [代理 C] 標題魔法師 (Headline Agent)
    console.print("[yellow]🤖 代理 C (標題大師) 正在生成爆款標題...[/yellow]")
    agent_c_role = "你是擁有頂級文案能力的標題黨大師，知道如何讓人忍不住點擊，但絕不使用低俗農場文套路。"
    agent_c_prompt = "請根據剛剛寫出的 Threads 貼文，想出 5 個極具吸引力的標題。每個標題必須包含一行主標題與一行副標題。主標題要有鉤子，副標題交代價值所在。"
    headlines = ask_llm(agent_c_prompt, threads_copy, agent_c_role, "gemini-2.5-flash")
    console.print(Panel(Markdown(headlines), title="✨ 爆款標題池", border_style="cyan"))
    
    console.print("\n[bold green]✅ Pipeline 執行完畢！您可以直接拷貝上方的 Threads 文案與標題。[/bold green]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Content Agent - Obsidian -> Threads 自動化多代理流水線")
    parser.add_argument("source", nargs="?", help="輸入來源 (網址、檔案路徑、或純文字)。若留空則讀取系統剪貼簿。")
    args = parser.parse_args()
    
    source_text = get_input_text(args.source)
    run_pipeline(source_text)


if __name__ == "__main__":
    main()
