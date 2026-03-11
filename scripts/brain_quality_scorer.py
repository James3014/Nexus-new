import os
import re


def calculate_score(file_path):
    try:
        with open(file_path, "r", errors="ignore") as f:
            content = f.read()

        score = 0
        # 1. 結構化檢查 (+30)
        if "---" in content:
            score += 15
        if "items:" in content:
            score += 15

        # 2. 連結密度檢查 (+40)
        links = re.findall(r"\[\[.*?\]\]", content)
        if len(links) >= 3:
            score += 20
        if len(links) >= 10:
            score += 20

        # 3. 語義深度 (+30)
        if "insights:" in content:
            score += 15
        if len(content) > 500:
            score += 15

        return score
    except:
        return 0


def run_iq_audit():
    print("🧠 Brain-IQ-Scorer: Measuring knowledge quality...")
    vault_root = "知識庫"
    results = []

    for root, dirs, files in os.walk(vault_root):
        dirs[:] = [
            d
            for d in dirs
            if d not in ["00_System_Knowledge", "01_Operations", "scripts", ".git"]
        ]
        for file in files:
            if file.endswith(".md") and file != "README.md":
                path = os.path.join(root, file)
                score = calculate_score(path)
                results.append((file.replace(".md", ""), score))

    results.sort(key=lambda x: x[1], reverse=True)
    avg_score = sum(s for n, s in results) / len(results) if results else 0

    report_path = "知識庫/01_Operations/Brain_Reports/Brain_IQ_Map.md"
    with open(report_path, "w") as f:
        f.write("# 🧠 Muse-Core 大腦 IQ 戰力地圖\n\n")
        f.write(f"> **平均智商 (Avg IQ)**: {avg_score:.2f} / 100\n")
        f.write(f"> **掃描樣本數**: {len(results)}\n\n---\n\n")

        f.write("## 🏆 高品質結晶 (Top 10)\n")
        for name, score in results[:10]:
            f.write(f"- [[{name}]] (IQ: {score})\n")

        f.write("\n## 🏚️ 待補強草稿 (Bottom 10)\n")
        for name, score in results[-10:]:
            f.write(f"- [[{name}]] (IQ: {score})\n")

    print(f"✅ IQ Audit complete. Average Score: {avg_score:.2f}")


if __name__ == "__main__":
    run_iq_audit()
