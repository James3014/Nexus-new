# Nexus v27.2 Topic Taxonomy & Capability Map

本文件定義了 Nexus 演進至 v27.2 的「題庫分類學 (Taxonomy)」。我們不再將 123 題視為單一整體，而是拆分為 6 大能力家族，以便執行 **逐族 TDD 擴張** 與 **受控放量**。

## 📊 題庫能力分布

### Django_ORM_Migration
- **定義**: Django ORM 元數據與遷移隱性依賴 (如 Meta attributes, db_table)
- **題目數量**: 3 題
- **涵蓋任務**: `django-v27-12, django-v27-15, django-v27-18`

### Django_Core_Logic
- **定義**: Django 框架核心邏輯與 HTTP 請求處理
- **題目數量**: 7 題
- **涵蓋任務**: `django-v27-10, django-v27-11, django-v27-13, django-v27-14, django-v27-16 ...`

### Astropy_Astrophysics
- **定義**: Astropy 物理計算、座標轉換與單位處理
- **題目數量**: 5 題
- **涵蓋任務**: `astropy-v27-1, astropy-v27-3, astropy-v27-5, astropy-v27-7, astropy-v27-9`

### Astropy_IO_FITS
- **定義**: Astropy 檔案解析 (FITS/ASCII) 與格式相容性
- **題目數量**: 5 題
- **涵蓋任務**: `astropy-v27-0, astropy-v27-2, astropy-v27-4, astropy-v27-6, astropy-v27-8`

### Concurrency_Race_Condition
- **定義**: 多執行緒、非同步屏障與競爭條件 (Race Conditions)
- **題目數量**: 10 題
- **涵蓋任務**: `concurrency-0, concurrency-1, concurrency-2, concurrency-3, concurrency-4 ...`

### Cross_Domain_Experimental
- **定義**: Scikit-learn, Flask 等跨域遷移驗證
- **題目數量**: 2 題
- **涵蓋任務**: `v27-sklearn-001, v27-flask-002`

---
## 🚀 下一步 (Next Steps)
1. 從上述某一家族 (如 `Django_ORM_Migration`) 挑選 3 題代表題。
2. 在 `nexus/governance/domain` 內擴充對應的 `VerifierPack` (如 `DjangoSemanticVerifier`)。
3. 走完 TDD 紅綠循環後，提報 Auto-Promotion 收據。
