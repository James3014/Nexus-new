# Nexus × Knowledge Agent：讓本地小模型打平前沿大模型的整合方案

> 基於 Knowledge Agent 方法論（來源: weightythoughts.com）與 Nexus LocalHeal 架構的結合分析

---

## 一、Knowledge Agent 核心概念

### 1.1 四種知識文件類型

| 文件類型 | 目的 | 範例 |
|---------|------|------|
| **原始萃取 (Raw Extraction)** | 未經加工的原始文本、會議紀錄、研究摘要 | 泰國央行會議紀錄原文 |
| **概念文件 (Concept Files)** | 百科條目式的結構化知識 | 「通貨膨脹政策框架」定義 |
| **論點文件 (Argument Files)** | 跨主題的綜合分析 | 「數位貨幣對匯率穩定的影響」 |
| **入門指南 (Onboarding Guide)** | Agent 定位用的元資料 | 任務類型對應的知識地圖 |

### 1.2 為什麼有效

- **查詢時即時撈出相關資訊**，塞進 prompt 上下文
- **多輪檢索**（最多三輪效果最好）
- **幾千份文件成本 < 1 美元**（embedding 用本地 BGE-M3 或 OpenAI 小模型）
- 連 27B 的 Qwen 都能追上前沿水準
- **核心洞察：當知識架構做對了，模型大小變成次要**

---

## 二、Nexus 現有基礎設施盤點

### 2.1 已存在的組件

| 組件 | 路徑 | 功能 | 可直接複用？ |
|------|------|------|-------------|
| MemoryRetrievalAdapter | `nexus/services/local_heal/memory_retrieval_adapter.py` | 多源記憶檢索（JSONL、FindingsMemory、MemoryRepository） | ✅ 擴充為知識檢索 |
| Embedding Service | `nexus/services/memory_embedding.py` | 本地 MiniLM-L6-v2 向量化（384-dim） | ✅ 可升級為 BGE-M3 |
| LanceDB Storage | `nexus/infrastructure/storage_implementations.py` | 向量資料庫基礎設施 | ✅ 已有框架 |
| SemanticSearcher | `nexus/services/semantic_searcher.py` | FTS 搜尋 + 檢索收據 | ✅ 可嵌入知識查詢 |
| OllamaLocalModelProvider | `nexus/services/local_heal/local_model_provider.py` | 本地模型呼叫（Ollama） | ✅ 已就緒 |
| CompositeLessonStore | `nexus/services/local_heal/memory_retrieval_adapter.py:151` | 多源組合查詢 | ✅ 核心架構直接複用 |
| LearningClosureBridge | `nexus/services/local_heal/learning_closure_bridge.py` | 學習經驗回寫 | ✅ 可轉為知識回寫 |

### 2.2 關鍵缺口（Sprint B 前的現狀）

| 缺口 | 影響 | 解法 |
|------|------|------|
| **10/14 June LocalHeal 組件不可達** | 本地模型繞過 CodeIntel、Research、Memory | Knowledge Agent 填補知識空白 |
| **LanceDB local_model_supported=False** | 無本地向量檢索 | 新增知識檢索層 |
| **Memory is METADATA_ONLY** | 記憶被動、不參與決策 | 知識注入改為主動 |
| **Embedding 用 384-dim MiniLM** | 語義精細度不足 | 升級 BGE-M3（多語言） |
| **無知識文件分類機制** | 只有 lesson 成功/失敗二分法 | 四種知識文件類型 |

---

## 三、整合架構設計

### 3.1 知識框架層（Knowledge Framework Layer）

```
┌─────────────────────────────────────────────────┐
│                  Knowledge Agent                 │
│  ┌─────────────┐  ┌─────────────┐               │
│  │ Raw Extracts│  │  Concepts   │               │
│  │  (原文本)    │  │ (百科條目)   │               │
│  └──────┬──────┘  └──────┬──────┘               │
│         │                │                       │
│  ┌──────┴────────────────┴──────┐               │
│  │   KnowledgeRetriever         │               │
│  │   (Semantic + BM25 混合)     │               │
│  └──────────────┬───────────────┘               │
│  ┌─────────────┐  ┌─────────────┐               │
│  │  Arguments  │  │  Onboarding │               │
│  │ (論點文件)   │  │  (導航)     │               │
│  └─────────────┘  └─────────────┘               │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│              Nexus LocalHeal Pipeline            │
│  ┌──────────────┐  ┌────────────────────┐       │
│  │  Ollama      │  │  KnowledgeEnricher │       │
│  │  Provider    │◄─┤  (Prompt 知識注入) │       │
│  └──────────────┘  └────────────────────┘       │
│  ┌──────────────┐  ┌────────────────────┐       │
│  │  Verifier    │  │  LearningClosure   │       │
│  └──────────────┘  └────────────────────┘       │
└─────────────────────────────────────────────────┘
```

### 3.2 知識文件的索引流程

```
原始文件 → [BGE-M3 Embedding] → LanceDB 知識表
                                        ↓
用戶查詢 → [Query Embedding] → 向量相似度 Top-K → [Rerank by type] → 注入 Prompt
                                        ↓
                              [BM25 混合排序]
```

### 3.3 多輪檢索機制（最多三輪）

```
Round 1: 廣域檢索 → 取得相關概念 + 原始萃取
Round 2: 聚焦檢索 → 基於 Round 1 結果深化論點文件
Round 3: 驗證檢索 → 確認一致性（可選）
```

---

## 四、實作方案

### 4.1 Phase 1：知識文件管理器

**新增檔案**: `nexus/services/knowledge_framework/`

| 檔案 | 職責 |
|------|------|
| `knowledge_store.py` | 知識文件的 CRUD + 向量化 |
| `knowledge_retriever.py` | 混合檢索（Semantic + BM25） |
| `knowledge_enricher.py` | Prompt 知識注入 |
| `knowledge_types.py` | 四種文件類型的定義 |
| `ingestion_pipeline.py` | 文件匯入 + 分類 |

```python
# knowledge_types.py — 四種知識文件類型
from enum import Enum
from dataclasses import dataclass

class KnowledgeFileType(str, Enum):
    RAW_EXTRACTION = "raw_extraction"    # 原始萃取
    CONCEPT = "concept"                  # 概念文件
    ARGUMENT = "argument"                # 論點文件
    ONBOARDING = "onboarding"           # 入門指南

@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    content: str
    file_type: KnowledgeFileType
    source: str
    topic_tags: tuple[str, ...]
    embedding: list[float] | None = None
    confidence: float = 1.0
```

### 4.2 Phase 2：升級 Embedding 為 BGE-M3

**修改檔案**: `nexus/services/memory_embedding.py`

```python
# 原始: MODEL_NAME = "all-MiniLM-L6-v2" (384-dim)
# 目標: BGE-M3 (1024-dim, 多語言, 稀疏+稠密混合)

BGE_M3_MODEL_NAME = "BAAI/bge-m3"
BGE_M3_DIM = 1024

class BGE_M3_EmbeddingService:
    """多語言知識檢索嵌入服務"""
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        # 使用 BGE-M3 產生稠密向量
        ...
    
    def embed_with_sparse(self, texts: list[str]) -> dict:
        """產生稠密 + 稀疏向量（混合檢索用）"""
        # BGE-M3 支持 ColBERT 風格的稀疏表示
        ...
```

成本估算：
- BGE-M3 本地推理：免費
- OpenAI `text-embedding-3-small`：$0.02/1M tokens
- 幾千份文件：< 1 美元

### 4.3 Phase 3：KnowledgeEnricher — Prompt 知識注入

**整合點**: `nexus/services/local_heal/local_model_provider.py` 的 `OllamaLocalModelProvider.generate()`

```python
class KnowledgeEnricher:
    """在模型呼叫前注入相關知識"""
    
    def enrich_prompt(
        self,
        base_prompt: str,
        query_text: str,
        max_rounds: int = 3,
        max_tokens: int = 2000,
    ) -> str:
        """
        三輪知識注入:
        1. 廣域檢索：概念 + 原始萃取
        2. 聚焦檢索：論點文件
        3. 驗證：一致性確認（可選）
        """
        context_parts = []
        seen_doc_ids = set()
        
        for round_num in range(max_rounds):
            results = self.retriever.retrieve(
                query=query_text,
                exclude_ids=seen_doc_ids,
                max_results=3,
            )
            if not results:
                break
            
            for doc in results:
                context_parts.append(
                    f"[{doc.file_type.value}] {doc.content[:500]}"
                )
                seen_doc_ids.add(doc.doc_id)
            
            # Token 預算檢查
            if self._estimate_tokens(context_parts) >= max_tokens:
                break
        
        knowledge_context = "\n\n".join(context_parts)
        return (
            f"## Relevant Knowledge\n{knowledge_context}\n\n"
            f"## Task\n{base_prompt}"
        )
```

### 4.4 Phase 4：文件匯入 CLI

```bash
# 匯入單一文件
nexus knowledge ingest --file report.md --type raw_extraction --topic "monetary_policy"

# 匯入整個目錄
nexus knowledge ingest --dir ./knowledge_base/ --recursive

# 檢索測試
nexus knowledge query "What are the impacts of digital currency on exchange rate stability?"

# 統計
nexus knowledge stats
```

---

## 五、與 Nexus 路由的整合

### 5.1 知識驅動的路由決策

```
Task 來 → CapabilityPlanner → 路由決策
                    ↓
              KnowledgeRetriever → 知識命中率
                    ↓
         ┌─────────┴─────────┐
         │  命中率 > 閾值     │  命中率 < 閾值
         │  → 本地模型+知識   │  → 雲端模型
         └─────────┬─────────┘
                   ↓
         LocalModelExecutor + KnowledgeEnricher
```

### 5.2 知識命中率作為路由信號

```python
# 在 CapabilitySelector 中新增知識維度
class KnowledgeHitSignal:
    """知識命中率作為路由決策的額外信號"""
    
    def evaluate(self, task_description: str) -> float:
        """
        回傳 0.0-1.0 的知識命中分數
        - 1.0: 知識庫有高度相關文件 → 本地模型可行
        - 0.0: 無相關知識 → 需要雲端模型
        """
        results = self.knowledge_retriever.retrieve(
            query=task_description, limit=5
        )
        if not results:
            return 0.0
        return min(1.0, len(results) / 5.0 * max(r.confidence for r in results))
```

### 5.3 成本路由矩陣

| 知識命中率 | 模型選擇 | 估計成本 |
|-----------|---------|---------|
| > 0.8 | 本地 7B/14B + 知識框架 | ~$0 |
| 0.5–0.8 | 本地 + 知識 + 雲端驗證 | ~$0.01–0.05 |
| < 0.5 | 雲端模型 (Gemini/Opus) | ~$0.01–0.10/task |

---

## 六、實際效益估算

### 6.1 以泰國央行案例為基準

| 指標 | 原始 | Knowledge Agent + 27B |
|------|------|---------------------|
| Claude Opus 4.8 | 基準 | ~持平 |
| Sonnet | ~持平 | ~持平 |
| DeepSeek v4 Pro | ~持平 | ~持平 |
| Qwen 3.6 27B | 落後 | **追上前沿水準** |
| 月 token 費用 | $2000–3000 | **~$0**（本地推論） |
| 文件處理成本 | — | < $1（幾千份） |

### 6.2 Nexus 特定效益

| 面向 | Before | After |
|------|--------|-------|
| 本地模型可用能力 | 5/34（LocalHeal only） | 20+/34（Knowledge 充填） |
| 記憶參與決策 | METADATA_ONLY | 主動知識注入 |
| 路由決策維度 | Task 複雜度 + 歷史 | + 知識命中率 |
| 月推論成本（100 tasks） | ~$5–15（本地） | ~$0（本地）+ 知識 |

---

## 七、風險與緩解

| 風險 | 緩解 |
|------|------|
| 知識過時（stale context） | 學習回寫 + 定期重新索引 |
| 向量檢索延遲（多輪） | 本地 BGE-M3 + 快取；上限三輪 |
| 知識衝突（矛盾文件） | 論點文件優先級 + 時間戳記 |
| 本地模型理解力不足 | 小模型 + 知識 > 大模型無知識（已驗證） |
| 文件分類錯誤 | 自動分類 + 人工校正回路 |

---

## 八、下一步行動

1. **立即**：建立 `nexus/services/knowledge_framework/` 目錄結構
2. **短期**：實作 KnowledgeStore + BGE-M3 embedding
3. **中期**：整合 KnowledgeEnricher 到 OllamaLocalModelProvider
4. **長期**：建立文件匯入 CLI + 多輪檢索機制

---

## 參考

- Knowledge Agent 原文: https://weightythoughts.com/p/knowledge-agents-beat-frontier-models
- Nexus LocalHeal: `nexus/services/local_heal/`
- Memory Retrieval: `nexus/services/local_heal/memory_retrieval_adapter.py`
- Embedding Service: `nexus/services/memory_embedding.py`
- Ollama Provider: `nexus/services/local_heal/local_model_provider.py`
- Capability Wiring: `nexus/services/local_heal/local_model_capability_wiring.py`
