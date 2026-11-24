# 版本變更紀錄（Changelog）

本文件記錄 **LoadPulse** 澳洲 AEMO NEM 電力負載資料工程管線之各版本結構、口徑與輸出變更。

---

## 2026-11-24 (v2.1.0)

### 新增
- **按 UTC 年份分表之 SQLite 資料庫輸出**：於 `data_pipeline/core_pipeline.py` 與 `data_pipeline/run_australia_pipeline.py` 新增 `AU_AEMO_NEM_hourly_1999_2026.db` 自動建庫流程，依 `timestamp_utc` 年份建立 `nem_1999`、`nem_2000`、…、`nem_2026` 共 **28 張獨立年表**（`nem_1999`–`nem_2005` 含 4 州、`nem_2006`–`nem_2026` 含 5 州），每張年表均設定 `PRIMARY KEY (region_id, timestamp_utc)` 並建立 `(region_id, local_date)` 查詢索引。

### 修正
- **對齊完整 UTC 起始年份邊界**：
  - `NSW1`、`QLD1`、`SA1`、`VIC1` 裁切自完整年份起點 `1999-01-01 00:00:00+00:00` 起算（移除 1998 年 12 月非完整開市週次）。
  - `TAS1` 裁切自完整年份起點 `2006-01-01 00:00:00+00:00` 起算（移除 2005 年 5–12 月非完整併網年份）。
  - `2026` 年維持現有最新時段（至 `2026-11-17 13:00:00+00:00`）不裁切；`1999–2025` 各完整 UTC 年每州均無時間軸缺口（平年 `8,760` 筆、閏年 `8,784` 筆），全庫總列數更新為 **`1,160,542`** 筆。
- **產物命名同步更新**：清洗後雙 Parquet 更名為 `AU_AEMO_NEM_hourly_1999_2026.parquet`（13 欄主訓練長表）與 `AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet`（25 欄完整稽核長表），並清理舊版 `1998_2026` 逐時 Parquet 產物避免混淆。

### 移除
- **移除緊急停班覆寫與 `BOTH` 類別，精簡 `day_type` 為純三分類**：
  - 停用 `au_emergency_closures.csv` 覆寫邏輯，自輸出資料集移除 `is_emergency_closure`、`emergency_event_category` 與 `emergency_scope` 欄位，不再產出 `EMERGENCY_CLOSURE` 與 `BOTH` 日型。
  - `day_type` 嚴格收斂為 **`PUBLIC_HOLIDAY` > `WEEKEND` > `WEEKDAY`** 純三分類：凡 `is_public_holiday == 1`（含法定跨週末補假），無論是否落在週六日一律標記為 `PUBLIC_HOLIDAY`（`36,158` 筆）；非國定假日之週六日標記為 `WEEKEND`（`325,301` 筆）；其餘一律標記為 `WEEKDAY`（`799,083` 筆）。

---

## 2026-11-23 (v2.0.0)

### 新增
- 建立 `data_pipeline/build_raw_parquet.py`，將 1,603 份官方月 CSV 無損打包為 `AU_AEMO_NEM_raw_1998_2026.parquet` 並產出 `raw_bundle_manifest.json` 三層 SHA-256 指紋清單。
- 導入五州真實民用 IANA 時區、夏令時間（`is_dst` / `is_dst_transition`）、靜態國定假日（`au_public_holidays.csv`）與 WHO 疫情期間旗標（`is_covid_period`）。

### 修正
- 由單月寬表重構為複合主鍵 `(region_id, timestamp_utc)` 之全歷史向量化長表，分段處理 `2021-10-01` 30min→5min 結算切換，並停用硬性 MW 上下限與 `1.5×IQR` 過濾以保留 `SA1` 屋頂光電倒灌負淨負載。

---

## 2026-11-17 (v1.0.0)

### 新增
- 完成初始跨國資料源評估與 `2021-01` 單月寬表清洗 Pilot 管線基準。
