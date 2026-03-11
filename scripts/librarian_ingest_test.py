import os
import re

def simulate_ingest(file_paths):
    print("🧠 Librarian-Ingest: Processing Resources into Layers...")
    
    memory_layers = {
        "Resources": [],
        "Items": [],
        "Insights": []
    }

    for path in file_paths:
        path = path.strip()
        if not os.path.exists(path): continue
        
        with open(path, "r", errors="ignore") as f:
            content = f.read()
            name = os.path.basename(path).replace(".md", "")
            
            # Layer 1: Resource
            memory_layers["Resources"].append(name)
            
            # Layer 2: Items (模擬提取參數)
            # 尋找 角度、公分、重心等具體數值
            angles = re.findall(r"(\d+度)", content)
            params = re.findall(r"(重心[^\s，。]*)", content)
            for a in angles: memory_layers["Items"].append(f"Angle: {a} (from {name})")
            for p in params: memory_layers["Items"].append(f"Param: {p} (from {name})")
            
            # Layer 3: Insights (模擬語義總結)
            if "重心" in content and "發力" in content:
                memory_layers["Insights"].append(f"核心關聯: 重心位移決定發力效率 (Found in {name})")

    # 產出報告
    report_path = "知識庫/01_Operations/Librarian_Ingest_Test_Report.md"
    with open(report_path, "w") as f:
        f.write("# 🧠 Librarian-Ingest 模擬測試報告\n\n")
        f.write("## 📄 Layer 1: Resources (原始檔案)\n")
        for r in memory_layers["Resources"]: f.write(f"- [[{r}]]
        
        f.write("\n## 💎 Layer 2: Items (結構化物件)\n")
        for i in memory_layers["Items"]: f.write(f"- {i}\n")
        
        f.write("\n## 💡 Layer 3: Insights (跨域洞察)\n")
        for ins in set(memory_layers["Insights"]): f.write(f"- {ins}\n")
    
    print(f"✅ Ingest completed. Report generated at {report_path}")

if __name__ == "__main__":
    with open("/Users/jameschen/Downloads/scripts/samples.txt", "r") as f:
        samples = f.readlines()
    simulate_ingest(samples)
