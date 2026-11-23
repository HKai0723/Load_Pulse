# LoadPulse 資料工程管線改版說明（Ver 2.0 vs Ver 1.0）

本文件系統性記錄 LoadPulse 澳洲電力負載清洗與標準化管線自 **Ver 1.0（單月 Pilot 寬表版）** 升級至 **Ver 2.0（全歷史 28 年長表＋三層 SHA-256 溯源版）** 的核心變更，供團隊成員快速對齊資料契約、工程架構與下游模型介接規範。

---

## 版本核心規格對照總覽

| 比較維度 | Ver 1.0（Pilot 基準版） | Ver 2.0（全歷史正式版） |
| :--- | :--- | :--- |
| **資料範圍** | 單月 `2021-01`（744 小時） | 全歷史 `1998-12` ~ `2026-11`（28 年，`1,168,495` 州-小時） |
| **原始輸入介面** | 逐檔讀取平鋪單月 CSV（`AU_AEMO_{REGION}_RAW_202101.csv`） | 先經 `build_raw_parquet.py` 無損打包 1,603 月 CSV 為單一 ZSTD Parquet，再由管線啟動驗真載入 |
| **資料表結構** | 五州橫向寬表（PK: `timestamp_utc`） | 五州縱向長表（複合 PK: `(region_id, timestamp_utc)`） |
| **輸出檔案格式** | `.csv`（`utf-8-sig`，寬表＋稽核寬表） | `.parquet`（`pyarrow` + `ZSTD`，主訓練表 `9.51 MB` / 14 欄、稽核表 `10.65 MB` / 28 欄） |
| **原始取樣頻率處理** | 固定假設 `30min` | 分段判定 `<= 2021-10-01 00:00:00` 減 `30min`、`>` 該時點減 `5min`，無縫銜接 5MS 切換 |
| **時區與日曆基準** | 全市場單一時區 `Australia/Brisbane`（無 DST） | 市場轉 UTC 後，依各州實際民用 IANA 時區（含 `SA1` 半小時與 4 州 DST）產出當地日曆 |
| **事件與日型特徵** | 僅 `hour`、`day_of_week`、`is_weekend` | 整合國定假日、緊急停班與疫情期，新增互斥五分類 `day_type` 與 4 個獨立二元旗標 |
| **異常值處理原則** | 硬邊界 `100–20,000 MW` ＋ 全域 `1.5×IQR` 標記離群值 | 停用硬性 MW 上下限與 IQR 離群過濾，保留 `SA1` 負淨負載；僅檢核結構性缺值與樣本數 |
| **計算引擎與相容性** | 含列級 Python `.apply()`，針對舊版 `pandas` | 全面向量化（零列級 `.apply()`），完全相容 `pandas 3.0.2` CoW 與混合時間格式（0 警告） |
| **版本與溯源機制** | 常數 `pipeline_version = "1.0.0"`，無雜湊指紋 | 三層 SHA-256 溯源：`raw_bundle_manifest.json`、列級 `source_file_sha256`/`version`、Parquet Schema Metadata |

---

## 一、多了什麼（Added）

1. **無損原始整合層與總指紋清單（`build_raw_parquet.py`）**：
   - 新增 `data_pipeline/build_raw_parquet.py`，啟動時驗證全部 `1,603` 份官方月 CSV 之實際 SHA-256 與 `raw_manifest.json` 100% 相符，無損打包為 `AU_AEMO_NEM_raw_1998_2026.parquet`（`4,585,729` 筆、`28.74 MB`）。
   - 產出 `data/processed/raw_bundle_manifest.json`，同時提供頂層快篩總指紋 `master_sources_sha256` 與全部 `1,605` 份來源檔（1,603 原始 CSV + 2 外部 CSV）的獨立 64 碼 SHA-256 明細。
2. **三層 SHA-256 端對端溯源機制**：
   - **啟動閘道驗真**：`run_australia_pipeline.py` 啟動即核對原始整合 Parquet 與兩份外部 CSV 的實際 SHA-256，任一檔案遭竄改或未同步即中止。
   - **列級溯源欄位（`full_qc` 表）**：新增 `source_file`、`source_file_sha256`（完整 64 碼，缺失小時為 `None`）與 SemVer 複合版本欄 `version`（如 `v2.0.0+src.937f330e39c2+raw.ba37ed923620`）。
   - **檔頭 Schema Metadata（雙 Parquet 皆含）**：透過 `pa.Schema.with_metadata` 寫入 6 項完整 64 碼稽核資訊（`pipeline_version`、`master_sources_sha256`、`input_raw_parquet_sha256`、`external_holidays_sha256`、`external_emergency_sha256`、`generated_at_utc`）。
3. **外部國定假日、災害緊急停班與五分類 `day_type`**：
   - 新增 `src/data_collection/fetch_au_holidays.py` 產出 `data/external/au_public_holidays.csv`（`1,519` 筆），並整合人工編彙之災害停班表 `data/external/au_emergency_closures.csv`（`322` 州-日、44 起獨立災害事件）。
   - 新增嚴格互斥五分類 `day_type`（`WEEKDAY`、`WEEKEND`、`PUBLIC_HOLIDAY`、`EMERGENCY_CLOSURE`、`BOTH`）與獨立二元旗標 `is_public_holiday`、`is_emergency_closure`；同時保留 `holiday_name`、`emergency_event_category`、`emergency_scope` 於 `full_qc` 表。
4. **COVID-19 期間標記（`is_covid_period`）**：
   - 依 WHO 國際關注公共衛生緊急事件期間（`2020-01-30` 至 `2023-05-05`）標註 `is_covid_period = 1`（共 `143,044` 小時），讓模型訓練端彈性過濾而不破壞原始歷史連續性。
5. **各州真實民用時區與夏令時間（DST）特徵**：
   - 依 `region_id` 對應五州民用 IANA 時區（`Australia/Sydney`、`Australia/Brisbane`、`Australia/Adelaide`、`Australia/Hobart`、`Australia/Melbourne`），新增 `is_dst`（當地是否實施夏令時間，共 `441,715` 小時）與 `is_dst_transition`（`211` 次夏令切換小時）。
6. **每小時實收樣本數與結構性完整度稽核欄位**：
   - 於 `full_qc` 表新增 `raw_interval_min`（`30` 或 `5`）、`sample_count`、`expected_samples`（`2` 或 `12`）與 `is_partial_hour`（全歷史共 `29` 筆），精準辨識非滿樣本小時。

---

## 二、少了什麼（Removed）

1. **停用硬性 MW 上下限與 `1.5×IQR` 離群值判定（`validate_load_values` / `is_suspected_outlier`）**：
   - 實測證實南澳（`SA1`）因高滲透率屋頂光電倒灌，全歷史有 `1,581` 筆 5 分鐘區間與 `124` 小時淨負載 `<= 0 MW`（逐時最低 `-280.12 MW`、5 分鐘最低 `-311.10 MW`），且跨 28 年長期趨勢會使全域 IQR 嚴重失真；故 Ver 2.0 全面移除 `100–20,000 MW` 邊界與 `is_suspected_outlier` 旗標。
2. **移除不再使用之冗餘稽核旗標與欄位**：
   - 自輸出資料集捨棄未啟用之 `is_imputed`、`is_source_revised` 與舊版 `raw_timestamp` 欄位；同時於載入原始 Parquet 時即透過欄位投影捨棄 `RRP` 與 `PERIODTYPE`，使訓練長表精簡聚焦於電力負載。
3. **移除單月 CSV 輸出與丹麥／美國多國支線**：
   - 不再產出 `AU_AEMO_NEM_hourly_202101*.csv` 與抽樣 CSV；舊期丹麥（Energinet）與美國（EIA）管線、視覺化函式及報告均已封存至 `archive/`。
4. **移除全表列級 Python `.apply()`**：
   - 移除 `core_pipeline.py` 原有 `utcoffset().total_seconds()`、`quality_flag` 之 `.apply(axis=1)` 與 `isoformat()` 逐列迴圈，消除百萬列效能瓶頸。

---

## 三、改了什麼（Changed）

1. **表結構由「五州寬表」改為「標準化長表」**：
   - 由單月 `744` 列寬表（每州展開 `*_load_mw`、`*_quality_flag`）改為全歷史 `1,168,495` 列長表，複合主鍵 `(region_id, timestamp_utc)`，更契合多區聯合深度學習模型（如 PatchTST、TFT、LightGBM）與分組特徵工程。
2. **時間網格由「全局固定起訖」改為「分區實際併網起訖」**：
   - `NSW1`/`QLD1`/`SA1`/`VIC1` 自 `1998-12-06 15:00Z` 起算（各 `244,991` 列），`TAS1` 自實際併網日 `2005-05-16 03:00Z` 起算（`188,531` 列），避免為 `TAS1` 併網前 77 個月（官方 404）平白製造 `56,460` 筆假缺失列。
3. **跨期時間解析與區間平移重構**：
   - 改以 `pd.to_datetime(..., format="mixed")` 統一相容三代官方時間格式（`199812`–`200310` 無秒、`200311`–`201605` 雙引號含秒、`201606+` 無引號含秒），並以 `2021-10-01 00:00:00 AEST` 為界分段平移 `30min` 與 `5min`，統一時間精度為 `as_unit("s")`。
4. **聚合引擎與 `pandas 3.0.2` 全面對齊**：
   - 以 `timestamp_utc.dt.floor("h")` 搭配 `groupby(["region_id", "hour_utc"])` 取代舊版逐區 `.resample("1h")`，並透過向量化偏移減法與 `np.select` 計算 `is_dst`、`is_dst_transition`、`day_type` 與 `quality_flag`（精簡為 `OK` / `PARTIAL_HOUR` / `MISSING`），全流程於 Python 3.13 + `pandas 3.0.2`（Copy-on-Write 強制啟用）下以 `-W always` 執行達成 **45 秒內完成且 0 警告**。
5. **儲存格式與壓縮效率大幅升級**：
   - 採用 `pyarrow` 顯式 `pa.Schema`（低基數字串採 `dictionary<int16, string>`、布林／小整數採 `int8`）搭配 `ZSTD` 壓縮：458 萬筆原始 CSV（`202.76 MB`）壓縮為 `28.74 MB`，116.8 萬筆逐時主訓練表僅 `9.51 MB`、28 欄完整稽核表僅 `10.65 MB`，全部安全低於 GitHub 單檔建議限制。
6. **視覺化與品質報告同步全面升級**：
   - `plot_quality_report.py` 與 `plot_region_maps.py` 改用無頭 `Agg` 模式與全英文圖表標籤，啟動即驗證 Parquet Metadata SHA-256，產出涵蓋 1998–2026 長期趨勢、2025 代表週鴨子曲線、民用時區熱圖、五分類 `day_type` 負載影響與 NEM 五州地理分佈等 4 張高解析檢核圖表。
