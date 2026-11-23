# LoadPulse 資料清洗管線 10 大功能與品質規格書（v2.0.0）

本規格書詳細說明 `data_pipeline/core_pipeline.py`（`PIPELINE_VERSION = "2.0.0"`）與 `data_pipeline/run_australia_pipeline.py` 之技術實作規範、10 項標準化管線能力對應、異常值處理原則轉變，以及全歷史 `1,168,495` 筆之實測品質稽核基準。

---

## 1. 管線 10 大核心功能拆解與 `core_pipeline.py` (v2.0.0) 對應

為兼顧百萬列執行效能與 `pandas 3.0.2` 向量化設計，v2.0.0 將原規範之 10 項標準化能力重構整合為 `core_pipeline.py` 內 7 支無列級迴圈（zero row-wise `.apply()`）之核心函式：

| 能力編號 | 標準化管線能力 | v2.0.0 實作函式（行號） | 輸入 / 輸出 | 核心處理邏輯 |
| :-: | :--- | :--- | :--- | :--- |
| 1 | **SHA-256 驗真與唯讀載入** | `compute_sha256` ([L89–95](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L89-L95))<br>`verify_and_load_raw_parquet` ([L98–182](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L98-L182)) | In: manifest / raw Parquet / 2 external CSVs<br>Out: `(df_raw, lineage)` | 啟動即驗證 `AU_AEMO_NEM_raw_1998_2026.parquet` 與兩份外部 CSV 之實際 SHA-256；僅投影載入 `REGION`, `SETTLEMENTDATE`, `TOTALDEMAND`, `source_file`（捨棄 `RRP`, `PERIODTYPE`）。 |
| 2 | **混合時間解析與 UTC 對齊** | `parse_and_shift_timestamps` ([L188–221](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L188-L221)) | In: `df_raw`<br>Out: `df_intervals` | 以 `pd.to_datetime(..., format="mixed")` 解析無秒／含秒字串並斷言 `0` 筆 `NaT`；依市場時間 `2021-10-01 00:00:00` 分段往前平移 `30min` 或 `5min` 轉區間起點，以固定 `Australia/Brisbane` localize 後轉為 `UTC`（`as_unit("s")`）。 |
| 3 | **原始取樣間隔分段判定** | `parse_and_shift_timestamps` ([L195–196](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L195-L196)) | In: `dt_end`<br>Out: `raw_interval_min (int8)` | 依 `dt_end <= 2021-10-01 00:00:00` 判定 `30`，之後判定 `5`，確保 30min→5min 切換邊界無縫銜接。 |
| 4 | **原始粒度重複時間戳檢核** | `parse_and_shift_timestamps` ([L213–215](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L213-L215)) | In: `df_intervals`<br>Out: 斷言 0 重複 | 依 `(region_id, timestamp_utc)` 驗證原始區間唯一性（實測全庫 4,585,729 筆 `dup = 0`），異常即中止。 |
| 5 | **逐小時功率聚合** | `aggregate_hourly_and_build_grid` ([L227–246](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L227-L246)) | In: `df_intervals`<br>Out: `hourly` | 以 `timestamp_utc.dt.floor("h")` 分槽，按 `(region_id, hour_utc)` 計算 `load_mw`（算術平均）、`sample_count`（實收筆數）、`raw_interval_min` 與 `source_file`。 |
| 6 | **分區連續 1h 網格與缺口偵測** | `aggregate_hourly_and_build_grid` ([L248–288](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L248-L288)) | In: `hourly`<br>Out: `df_grid` | 按各州實際併網營運起訖建立連續 `1h` UTC 網格（避免為 `TAS1` 併網前補出假缺口）並 `left-merge`，缺口忠實保留 `load_mw = NaN` 絕不填 0 或插補。 |
| 7 | **結構性樣本完整度檢核**（取代舊版硬門檻／IQR 過濾） | `attach_structural_quality_flags` ([L294–319](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L294-L319)) | In: `df_grid`<br>Out: `df_flagged` | 計算 `is_missing`、`expected_samples`（`2` vs `12`）、`is_partial_hour`（`sample_count < expected_samples`）、`is_duplicate`（`0`），以 `np.select` 向量化組裝 `quality_flag`（`MISSING` / `PARTIAL_HOUR` / `OK`）。 |
| 8 | **各州民用時區與 DST 計算** | `attach_civil_calendar_and_events` ([L325–376](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L325-L376)) | In: `df_flagged`<br>Out: `df_cal` | 依 5 州民用 IANA 時區分組轉換，以向量化偏移減法計算 `is_dst` 與 `is_dst_transition`，並產出 `local_date`, `local_hour`, `day_of_week`, `is_weekend`, `timestamp_local`。 |
| 9 | **外部假日、緊急停班五分類與疫情標記** | `attach_civil_calendar_and_events` ([L378–453](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L378-L453)) | In: `df_cal` + 2 external CSVs<br>Out: `df_enriched` | 以 `(region_id, local_date)` 執行 `many_to_one` 左連接，產出獨立布林旗標、嚴格互斥五分類 `day_type`（`BOTH` / `EMERGENCY_CLOSURE` / `PUBLIC_HOLIDAY` / `WEEKEND` / `WEEKDAY`）與 `is_covid_period`。 |
| 10 | **溯源封裝與雙 ZSTD Parquet 輸出** | `attach_lineage_and_export_parquets` ([L459–560](file:///C:/school/Load_Pulse/data_pipeline/core_pipeline.py#L459-L560)) | In: `df_enriched`, `lineage`<br>Out: 2 `.parquet` 檔 | 映射逐列 `source_file_sha256` 與複合 `version` 字串，套用顯式 Arrow `pa.Schema`（低基數字串 `dictionary<int16, string>`）並嵌入 64 碼 Metadata 後以 `ZSTD` 寫出。 |

---

## 2. 異常值處理規範轉變：為何停用硬門檻與全域 `1.5×IQR`

Ver 1.0 單月 Pilot 曾套用 `100–20,000 MW` 物理硬邊界與全域 `1.5×IQR` 標記離群值，但在擴展至 28 年全歷史後經實測證實存在兩項根本缺陷，故 Ver 2.0 正式停用：

1. **高再生能源滲透下負淨負載屬真實物理現象**：
   - 南澳（`SA1`）表後屋頂太陽能滲透率居全球之冠，於春夏季晴朗假日正午經常發生發電量大於用電量之倒送電現象。全歷史原始 5 分鐘紀錄中 `SA1` 有 `4,292` 筆 `< 100 MW`、`1,581` 筆 `<= 0 MW`（最低 `-311.10 MW`），逐時平均亦有 `124` 小時 `<= 0 MW`（最低 `-280.12 MW`，發生於 `2025-12-25 13:30+10:30`）。任何硬性正值下限皆會錯誤抹殺現代鴨子曲線核心特徵。
2. **跨 28 年長期結構偏移導致全域 IQR 失真**：
   - 澳洲各州經歷人口與工業成長、屋頂光電普及與電氣化轉型，1998–2026 單一全域 IQR 無法正確反映各年代常態分佈，反而會將近年真實熱浪空調尖峰與光電正午低谷大量誤標為異常。
3. **現行結構性完整度替代規則**：
   - 全面保留所有官方結算物理觀測值，僅透過 `is_missing`（無樣本、`load_mw = NaN`）與 `is_partial_hour`（`0 < sample_count < expected_samples`）忠實揭露資料蒐集層級之結構缺損。

---

## 3. 全庫結構性品質量化基準（1,168,495 列）

| 檢核指標 | 全庫總計 | 分區 / 時期明細與說明 |
| :--- | :---: | :--- |
| **總列數（`(region_id, timestamp_utc)` 唯一）** | **`1,168,495`** | `NSW1`/`QLD1`/`SA1`/`VIC1` 各 `244,991`、`TAS1` `188,531` |
| **完全正常小時（`quality_flag == "OK"`）** | **`1,168,450`** (`99.9961%`) | 5 分鐘時期（`2021-10` 起 `224,880` 小時）達成 **`100.0000%` 全 `OK`** |
| **真實缺失小時（`is_missing == 1`）** | **`16`** (`0.0014%`) | 集中於 `1999-05-13`、`2000-05-13`、`2001-04-08` 四州同步缺漏（各 4h，`TAS1` 為 `0`）；2001-04-08 後逾 25.5 年零缺漏 |
| **部分樣本小時（`is_partial_hour == 1`）** | **`29`** (`0.0025%`) | 皆發生於 30 分鐘時期（實收 `1/2` 筆）：開市／併網首小時邊界 5 筆 ＋ 1999–2000 早期缺報 24 筆 |
| **重複主鍵（`is_duplicate == 1`）** | **`0`** (`0.0000%`) | 原始 458 萬筆與逐時 116.8 萬筆皆經程式斷言 `0` 重複 |
| **夏令時間切換小時（`is_dst_transition == 1`）** | **`211`** | `NSW1`/`SA1`/`VIC1` 各 `56`、`TAS1` `43`、`QLD1` `0` |

---

## 4. 三層 SHA-256 溯源機制精簡說明

為確保全流程可重現且防靜默漂移，管線內建三層指紋連動：
1. **源頭清單層**：`data/processed/raw_bundle_manifest.json` 記錄 1,605 份來源檔（1,603 原始 CSV + 2 外部 CSV）之獨立 SHA-256 與頂層總指紋 `master_sources_sha256`（`937f330e39c2e2ea...`）。
2. **檔頭 Metadata 層**：兩份清洗後 Parquet 檔頭皆嵌入 64 碼 `master_sources_sha256`、`input_raw_parquet_sha256`、`external_holidays_sha256`、`external_emergency_sha256` 與 `pipeline_version`。
3. **列級追溯層**：`full_qc` 表逐列記錄 `source_file`、`source_file_sha256` 與複合版本字串 `version`（`v2.0.0+src.937f330e39c2+raw.ba37ed923620`）。
