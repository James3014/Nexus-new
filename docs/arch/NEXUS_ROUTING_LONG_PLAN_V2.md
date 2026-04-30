# 🧬 Nexus 智慧路由整合長計劃 v2 (P1-P34)

## [總結]
新路由不是單純「選能力」，而是 Nexus 的中樞神經：它要把五支柱、技能、JIT、RLM、學習、自癒、抗幻覺、MSA 能力，全部串進 `S,P,X,D,R,A,C`。  
目標是讓 Nexus 從「很多能力的集合」變成「會判斷何時使用哪些能力、會驗證、會寫回、會變強」的 Meta-Framework。

---

## [核心模型]
```text
Task / Code Change / User Intent
  -> S: Scope & Constraints
  -> P: Capability + Skill Plan
  -> X: Recon / Research / CodeIntel
  -> D: Decide / Govern / Belief
  -> R: Repair / Execute / Self-heal
  -> A: Audit / Artifact / Claim
  -> C: Closure / Learning / Rule Lifecycle
  -> 下一次路由變聰明
```

---

## [五支柱角色]

| 支柱 | 在新路由中的角色 | 不可缺原因 |
|---|---|---|
| LanceDB | 戰術檢索，找相似案例與 RAG context | 沒它路由只看當下文字 |
| Memory | 長期經驗，知道過去哪些能力有效 | 沒它不會成長 |
| MemPalace | 治理硬約束，禁止越界能力/skill | 沒它容易為了通過測試犧牲安全 |
| Belief | 信心控制器，決定升級/降級/重算 | 沒它能力組合會太重或太輕 |
| Artifact | 客觀證據，證明能力真的產出 | 沒它 selected 會被誤當 active |
| Claim | 斷言驗證，決定能否公開宣稱 | 沒它報告不可採信 |

---

## [S,P,X,D,R,A,C 連貫性]

| Phase | What | Why | How |
|---|---|---|---|
| S | 任務範圍、風險、治理邊界 | 先決定哪些事不能做 | MemPalace、DomainFirewall、task type、file scope、budget |
| P | 能力與 skill 組合計劃 | 讓 Nexus 不是 preset | CapabilitySelector + SkillSlot + cost/risk policy |
| X | 偵查與補上下文 | 避免低資訊決策 | CodeIntel、Research、LanceDB、Memory、JIT impact |
| D | 診斷與決策 | 抗幻覺與防過度自信 | Belief、Autoreason、MemPalace、Swarm review |
| R | 執行與自癒 | 真正修復/生成/委派 | Hyper、DDTree、RLM R-loop、Drone、Nightshift |
| A | 驗收與審查 | 把「看起來對」變「有證據地對」 | Artifact、Claim、Ultra Review、JIT tests |
| C | 學習閉環 | 讓下次路由更好 | CapabilityReceipt、SkillReceipt、LearningClosure、OutcomeMemory |

---

## [執行階段階段清單 (P1-P34)]

| ID | 任務名稱 | 核心職責 | 驗收標準 |
|---|---|---|---|
| **P1** | 凍結能力契約 | 停止補丁式 keyword | 文件化所有能力 phase/依賴/evidence |
| **P2** | 抽 `CapabilityRegistry` | 去 god object | 從 planner 拆純資料 |
| **P3** | 抽 `CapabilitySignalSet` | 統一輸入 | signal snapshot 可測 |
| **P4** | 抽 `CapabilityConstraints` | 治理硬約束 | MemPalace/Artifact/Claim 不可被降級 |
| **P5** | 抽 `CapabilitySelector` | 單一 truth source | selector 產出 capability plan |
| **P6** | 加 `SkillSignalSet` | skill 變輔助訊號 | SkillsRouter 提供候選，不直接改 mode |
| **P7** | 加 `SkillSlot` | skill 變能力內操作手冊 | phase 限制清楚 |
| **P8** | 加 `CapabilityExecutionPlan` | 選擇變可執行 | phase DAG、parallel、dependency |
| **P9** | 加 `ExecutorControls` | plan 真控制執行 | 移除 manual flag 依賴 |
| **P10** | 加 `CapabilityReceipt` | selected 不等於 active | 產生能力使用證據 |
| **P11** | 加 `SkillReceipt` | skill 也要證明價值 | skill 不靠注入算成功 |
| **P12** | 接 LanceDB/Memory | 路由會用歷史 | similar cases、prior success/failure |
| **P13** | 接 Belief | 控制升級降級 | 低信心升級，高信心 light path |
| **P14** | 接 MemPalace | 防止越權 | skill/capability 都先審 |
| **P15** | 接 Artifact/Claim | 抗幻覺硬門 | 沒 evidence 不可 pass |
| **P16** | CodeIntel/JIT 接 selector | 路由吃客觀 code risk | impact、risk_reason |
| **P17** | Autoreason receipt | 正式化候選評審 | votes/winner/stop_reason |
| **P18** | DDTree receipt | 防假加速 | eligible/pruned/saved_steps |
| **P19** | Ultra Review receipt | 高風險治理可證明 | sandbox/repro/gate/report |
| **P20** | Swarm receipt | MSA 真蜂群 | role findings/consensus/owner |
| **P21** | Drone receipt | 委派真證據 | subtask artifact/worker/parent/gate |
| **P22** | Nightshift receipt | 長任務自癒 | recommended/invoked/recovered 齊 |
| **P23** | RLM X-loop | recursive research | budgeted iterations + trace |
| **P24** | RLM R-loop | recursive repair | 不直通成功，需 A gate |
| **P25** | Dynamic replan | 每階段重算 | A reject、timeout、low belief 觸發 |
| **P26** | OutcomeMemory | 路由會成長 | 寫回能力勝率/成本/trust mismatch |
| **P27** | Rule lifecycle | 會自我更新但不亂改 | observation -> recommendation -> active |
| **P28** | Report 去語義 | 公開報告可信 | `ab_eval` 只讀 receipt |
| **P29** | 舊 router facade | 淘汰舊路由 | `CapabilityRouter` 包 selector |
| **P30** | `AutonomicRouter` 降級 | 避免第四套路由 | 不直接改 mode |
| **P31** | `research_flow_service` 瘦身 | 關注點分離 | service 只 orchestrate |
| **P32** | Nexus-only benchmark | 先驗證路由 | 12 題本機，檢查 receipt coverage |
| **P33** | Gemini smoke | 小規模真比較 | 3 題 bare vs Nexus |
| **P34** | Gemini full report | 對外公開數據 | public claim gate PASS |
