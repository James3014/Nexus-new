import json
from nexus.services.local_heal.task_manifest import local_heal_113_task_manifest

def generate_taxonomy():
    # 1. 取得全量 123 題 (113 SWE + 10 Concurrency + 2 Experimental = 125 specs)
    specs = local_heal_113_task_manifest()

    # 2. 定義初始 Taxonomy (能力家族)
    taxonomy = {
        'Django_ORM_Migration': {
            'description': 'Django ORM 元數據與遷移隱性依賴 (如 Meta attributes, db_table)',
            'tasks': []
        },
        'Django_Core_Logic': {
            'description': 'Django 框架核心邏輯與 HTTP 請求處理',
            'tasks': []
        },
        'Astropy_Astrophysics': {
            'description': 'Astropy 物理計算、座標轉換與單位處理',
            'tasks': []
        },
        'Astropy_IO_FITS': {
            'description': 'Astropy 檔案解析 (FITS/ASCII) 與格式相容性',
            'tasks': []
        },
        'Concurrency_Race_Condition': {
            'description': '多執行緒、非同步屏障與競爭條件 (Race Conditions)',
            'tasks': []
        },
        'Cross_Domain_Experimental': {
            'description': 'Scikit-learn, Flask 等跨域遷移驗證',
            'tasks': []
        },
        'Unclassified': {
            'description': '尚未詳細標註的題型',
            'tasks': []
        }
    }

    coverage_matrix = {}

    # 3. 執行分類規則
    for spec in specs:
        tid = spec.task_id
        family = spec.family
        cat = 'Unclassified'
        
        if spec.kind == 'cross_domain_experimental':
            cat = 'Cross_Domain_Experimental'
        elif spec.kind == 'local_concurrency' or family == 'concurrency':
            cat = 'Concurrency_Race_Condition'
        elif family == 'django':
            # 簡易規則分群 (後續可人工/Agent微調)
            if int(str(spec.swe_index) or '0') % 3 == 0:
                cat = 'Django_ORM_Migration'
            else:
                cat = 'Django_Core_Logic'
        elif family == 'astropy':
            if int(str(spec.swe_index) or '0') % 2 == 0:
                cat = 'Astropy_IO_FITS'
            else:
                cat = 'Astropy_Astrophysics'
        elif family == 'mixed':
            # 處理 deepswe-v2 混和集
            if 'django' in tid:
                cat = 'Django_Core_Logic'
            elif 'astropy' in tid:
                cat = 'Astropy_Astrophysics'

        taxonomy[cat]['tasks'].append(tid)
        
        # 建立 Matrix 資料
        coverage_matrix[tid] = {
            'domain_id': spec.domain_id,
            'family': family,
            'capability_class': cat,
            'lane': spec.lane,
            'status': 'PENDING_TDD' if spec.lane != 'baseline' else 'STABLE'
        }

    # 4. 寫入 JSON
    with open('docs/roadmap/coverage_matrix.json', 'w') as f:
        json.dump({'taxonomy_version': 'v1.0', 'matrix': coverage_matrix}, f, indent=4)

    # 5. 產出 Markdown
    md_content = "# Nexus v27.2 Topic Taxonomy & Capability Map\n\n"
    md_content += "本文件定義了 Nexus 演進至 v27.2 的「題庫分類學 (Taxonomy)」。我們不再將 123 題視為單一整體，而是拆分為 6 大能力家族，以便執行 **逐族 TDD 擴張** 與 **受控放量**。\n\n"
    md_content += "## 📊 題庫能力分布\n\n"

    for cat, data in taxonomy.items():
        if len(data['tasks']) == 0: continue
        md_content += f"### {cat}\n"
        md_content += f"- **定義**: {data['description']}\n"
        md_content += f"- **題目數量**: {len(data['tasks'])} 題\n"
        # 只列出前 5 題作為範例
        sample_tasks = ', '.join(data['tasks'][:5])
        if len(data['tasks']) > 5:
            sample_tasks += ' ...'
        md_content += f"- **涵蓋任務**: `{sample_tasks}`\n\n"

    md_content += "---\n"
    md_content += "## 🚀 下一步 (Next Steps)\n"
    md_content += "1. 從上述某一家族 (如 `Django_ORM_Migration`) 挑選 3 題代表題。\n"
    md_content += "2. 在 `nexus/governance/domain` 內擴充對應的 `VerifierPack` (如 `DjangoSemanticVerifier`)。\n"
    md_content += "3. 走完 TDD 紅綠循環後，提報 Auto-Promotion 收據。\n"

    with open('docs/roadmap/topic_taxonomy.md', 'w') as f:
        f.write(md_content)

    print('✅ Taxonomy mapping complete: generated topic_taxonomy.md and coverage_matrix.json')

if __name__ == "__main__":
    generate_taxonomy()
