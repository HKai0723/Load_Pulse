# LoadPulse 澳洲 NEM 逐小時資料集獨立資料字典（Data Dictionary, v2.1.0）

本文件定義 LoadPulse `v2.1.0` 清洗管線產出之兩份標準化 Parquet 長表與按 UTC 年份分表 SQLite 資料庫欄位規格及下游特徵工程使用契約：

- **主訓練長表**：`data/processed/AU_AEMO_NEM_hourly_1999_2026.parquet`（`1,160,542` 列 × `13` 欄、`9.37 MB`、`ZSTD`）
- **完整稽核長表**：`data/processed/AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet`（`1,160,542` 列 × `25` 欄、`10.49 MB`、`ZSTD`）
- **按年分表 SQLite 資料庫**：`data/processed/AU_AEMO_NEM_hourly_1999_2026.db`（共 `28` 張年表 `nem_1999` ~ `nem_2026`、欄位與 `full_qc` 25 欄完全一致）
- **複合主鍵（Primary Key）**：`(region_id, timestamp_utc)`（嚴格唯一、`0` 重複、升冪排序）
- **各州時間覆蓋範圍**：
  - `NSW1`、`QLD1`、`SA1`、`VIC1`：`1999-01-01 00:00:00Z` ~ `2026-11-17 13:00:00Z`（各 `244,382` 列）
  - `TAS1`：`2006-01-01 00:00:00Z` ~ `2026-11-17 13:00:00Z`（`183,014` 列）

---

## 1. 主訓練長表欄位定義（13 欄）

| # | 欄位名稱 | Parquet 型別 (Arrow) | SQLite 型別 | 物理單位 | 實測值域 / 缺值數 | 業務定義與說明 |
| :-: | :--- | :--- | :---: | :---: | :--- | :--- |
| 1 | `region_id` | `dictionary<int16, string>` | `TEXT NOT NULL` | — | `{NSW1, QLD1, SA1, TAS1, VIC1}`（null: 0） | AEMO NEM 東澳五大調度區代碼（複合主鍵第 1 欄）。 |
| 2 | `timestamp_utc` | `timestamp[ms, tz=UTC]` | `TEXT NOT NULL` | UTC 時間 | `1999-01-01 00:00Z` ~ `2026-11-17 13:00Z`（null: 0） | 逐小時區間起點（Interval-Beginning）UTC 時間戳（SQLite 儲存格式為 `YYYY-MM-DDTHH:MM:SSZ`）。 |
| 3 | `local_date` | `string` | `TEXT NOT NULL` | 日期 | `1999-01-01` ~ `2026-11-18`（`YYYY-MM-DD`，null: 0） | 依各州真實民用 IANA 時區換算之當地日曆日期，用於對齊國定假日表。 |
| 4 | `local_hour` | `int8` | `INTEGER NOT NULL` | 小時 | `0` ~ `23`（null: 0） | 當地民用時間之小時整數（註：`SA1` 為半小時時區，UTC 整點對應當地 `HH:30`）。 |
| 5 | `day_of_week` | `int8` | `INTEGER NOT NULL` | 星期 | `1` ~ `7`（ISO-8601：`1`=週一、`7`=週日，null: 0） | 依當地民用時間計算之星期幾。 |
| 6 | `is_weekend` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（null: 0） | `day_of_week` 為 `6` 或 `7` 時標記 `1`，否則 `0`。 |
| 7 | `is_dst` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（`1`: `437,696`，`QLD1` 恆 `0`，null: 0） | 該州於該時刻是否處於當地夏令時間（Daylight Saving Time）。 |
| 8 | `load_mw` | `double` (`float64`) | `REAL` | MW | `-280.12` ~ `14,509.95`（null: `16`） | 電網逐小時平均淨調度負載（`TOTALDEMAND` 算術平均，不含表後屋頂光電；真實缺值保留 `NaN`/`NULL`，負值代表屋頂光電倒灌）。 |
| 9 | `day_type` | `dictionary<int16, string>` | `TEXT NOT NULL` | 類別 | `{PUBLIC_HOLIDAY, WEEKEND, WEEKDAY}`（null: 0） | **純三分類日型標籤**（優先序 `PUBLIC_HOLIDAY` > `WEEKEND` > `WEEKDAY`，詳見第 3.3 節）。 |
| 10 | `is_public_holiday` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（`1`: `36,158`，null: 0） | 該州當地日期是否為靜態法定國定假日（含法定跨週末補假；來源：`au_public_holidays.csv`）。 |
| 11 | `is_covid_period` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（`1`: `143,044`，null: 0） | `local_date` 落於 WHO 疫情緊急事件期間 `2020-01-30` ~ `2023-05-05`（含端點）標為 `1`。 |
| 12 | `is_missing` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（`1`: `16`，null: 0） | 該小時無任何官方原始結算紀錄（`load_mw` 為 `NaN`/`NULL`）時標為 `1`。 |
| 13 | `quality_flag` | `dictionary<int16, string>` | `TEXT NOT NULL` | 類別 | `{OK, PARTIAL_HOUR, MISSING}`（null: 0） | 結構性品質摘要旗標（`OK`: `1,160,502`、`PARTIAL_HOUR`: `24`、`MISSING`: `16`）。 |

---

## 2. `full_qc` 完整稽核長表與 SQLite 延伸欄位定義（第 14–25 欄）

`AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet` 與 SQLite 各年表（`nem_1999` ~ `nem_2026`）完整包含上述 13 欄，並附加以下 12 欄供品管稽核與溯源使用：

| # | 欄位名稱 | Parquet 型別 (Arrow) | SQLite 型別 | 物理單位 | 實測值域 / 缺值數 | 業務定義與說明 |
| :-: | :--- | :--- | :---: | :---: | :--- | :--- |
| 14 | `iana_tz` | `dictionary<int16, string>` | `TEXT NOT NULL` | 時區名稱 | 5 個 IANA 民用時區（null: 0） | `NSW1`: `Australia/Sydney`、`QLD1`: `Australia/Brisbane`、`SA1`: `Australia/Adelaide`、`TAS1`: `Australia/Hobart`、`VIC1`: `Australia/Melbourne`。 |
| 15 | `timestamp_local` | `string` | `TEXT NOT NULL` | ISO-8601 | 含冒號偏移字串（如 `1999-01-01T11:00:00+11:00`，null: 0） | 該州當地民用時間完整 ISO-8601 字串（保留 `+10:00`/`+11:00`/`+09:30`/`+10:30`，避免夏令回撥歧義）。 |
| 16 | `raw_interval_min` | `int8` | `INTEGER NOT NULL` | 分鐘 | `{30, 5}`（null: 0） | 該小時對應之 AEMO 原始結算週期：`2021-09-30 14:00Z` 前為 `30`，之後為 `5`。 |
| 17 | `sample_count` | `int8` | `INTEGER NOT NULL` | 筆數 | `0`、`1`、`2`、`12`（null: 0） | 該小時內實際彙整之有效原始結算區間筆數（缺值小時為 `0`）。 |
| 18 | `expected_samples` | `int8` | `INTEGER NOT NULL` | 筆數 | `{2, 12}`（null: 0） | 該小時理論應有之原始區間筆數（30 分鐘時期為 `2`，5 分鐘時期為 `12`）。 |
| 19 | `is_partial_hour` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（`1`: `24`，null: 0） | 非缺值但實收樣本數不足（`is_missing == 0` 且 `sample_count < expected_samples`）標為 `1`。 |
| 20 | `is_duplicate` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0}`（null: 0） | 複合主鍵重複檢核旗標（全庫已驗證為 `0`）。 |
| 21 | `is_dst_transition` | `int8` | `INTEGER NOT NULL` | 布林 (0/1) | `{0, 1}`（`1`: `210`，null: 0） | 當地 UTC 偏移量較前一小時發生變動（夏令開始或結束切換時刻）標為 `1`。 |
| 22 | `holiday_name` | `dictionary<int16, string>` | `TEXT` | 名稱 | 法定假日名稱（非假日為 `null`） | 對應 `au_public_holidays.csv` 之法定假日名稱；非假日為 `null`。 |
| 23 | `source_file` | `dictionary<int16, string>` | `TEXT` | 檔名 | 官方月 CSV 檔名（null: `16`） | 該小時所屬之原始月檔名（如 `AU_AEMO_NSW1_RAW_202512.csv`）；缺失小時為 `null`。 |
| 24 | `source_file_sha256` | `dictionary<int16, string>` | `TEXT` | Hex 字串 | 64 碼小寫 SHA-256（null: `16`） | 對應 `source_file` 之原始檔指紋；缺失小時為 `null`。 |
| 25 | `version` | `dictionary<int16, string>` | `TEXT NOT NULL` | 版本標籤 | `v2.1.0+src.<12>+raw.<12>`（null: 0） | 管線版本與頂層／底稿 SHA-256 複合標籤（完整 64 碼同步寫入 Parquet Schema Metadata）。 |

---

## 3. 下游特徵工程、日型邏輯與 SQLite 查詢規範

### 3.1 主鍵與連續年份時間軸契約
- `1999–2025` 所有完整 UTC 年份每州皆為無時間軸缺口之連續逐小時網格（平年 `8,760` 筆／州、閏年 `8,784` 筆／州）。
- 進行任何滯後（Lag）或滾動（Rolling）運算前，必須確保依 **`["region_id", "timestamp_utc"]` 升冪排序**，並於 `groupby("region_id")` 邊界內獨立執行。

### 3.2 滑動視窗與 Lag 特徵防跨越缺口原則
- 全庫共有 `16` 筆 `is_missing == 1`（集中於 1999–2001 年四州同步缺漏，`load_mw` 為 `NaN`/`NULL`）。
- 計算滯後特徵時，**嚴禁先用 `.dropna()` 壓縮序列再做 `.shift()`**；應維持連續 UTC 網格計算 `.shift()`，再於樣本建構階段排除含 `NaN` 之訓練視窗。

### 3.3 純三分類 `day_type` 優先順序說明
- `v2.1.0` 已移除緊急停班覆寫與 `BOTH` 類別，`day_type` 嚴格僅含以下三種互斥取值：
  1. **`PUBLIC_HOLIDAY`**（`36,158` 小時）：只要 `is_public_holiday == 1`（含週六日國定假日與法定跨週末補假），一律優先標記為 `PUBLIC_HOLIDAY`。
  2. **`WEEKEND`**（`325,301` 小時）：`is_public_holiday == 0` 且 `is_weekend == 1` 之一般週六、週日。
  3. **`WEEKDAY`**（`799,083` 小時）：`is_public_holiday == 0` 且 `is_weekend == 0` 之一般工作日（不含寒暑假、橋接日或非國定假日之年末平日）。
- 於 `2020-01-30 ~ 2023-05-05`（`is_covid_period == 1`）期間，國定假日與週末仍依上述規則照常分類，下游模型可直接以 `is_covid_period == 0` 篩選排除疫情期。

### 3.4 SQLite 按年分表結構與索引規範
- `AU_AEMO_NEM_hourly_1999_2026.db` 依 `timestamp_utc` 之 UTC 年份拆分為 `nem_1999` 至 `nem_2026` 共 **28 張表**：
  - `nem_1999` ~ `nem_2005`（4 州：NSW1, QLD1, SA1, VIC1）：平年每表 `35,040` 列、閏年（`nem_2000`, `nem_2004`）每表 `35,136` 列。
  - `nem_2006` ~ `nem_2025`（5 州：含 TAS1）：平年每表 `43,800` 列、閏年（`2008`, `2012`, `2016`, `2020`, `2024`）每表 `43,920` 列。
  - `nem_2026`（5 州，截至 `2026-11-17 13:00Z`）：共 `38,470` 列（每州 `7,694` 列）。
- 每張表皆設有複合主鍵 `PRIMARY KEY (region_id, timestamp_utc)` 與輔助索引 `idx_nem_{YYYY}_region_local_date (region_id, local_date)`，支援依單年或 `UNION ALL` 跨年高效查詢。
