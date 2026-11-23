# LoadPulse 澳洲 NEM 逐小時資料集獨立資料字典（Data Dictionary）

本文件定義 LoadPulse `v2.0.0` 清洗管線產出之兩份標準化 Parquet 長表欄位規格與下游特徵工程使用契約：

- **主訓練長表**：`data/processed/AU_AEMO_NEM_hourly_1998_2026.parquet`（`1,168,495` 列 × `14` 欄、`9.51 MB`、`ZSTD`）
- **完整稽核長表**：`data/processed/AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet`（`1,168,495` 列 × `28` 欄、`10.65 MB`、`ZSTD`）
- **複合主鍵（Primary Key）**：`(region_id, timestamp_utc)`（嚴格唯一、`0` 重複、升冪排序）

---

## 1. 主訓練長表欄位定義（14 欄）

| # | 欄位名稱 | Parquet 型別 (Arrow) | 物理單位 | 實測值域 / 缺值數 | 業務定義與說明 |
| :-: | :--- | :--- | :---: | :--- | :--- |
| 1 | `region_id` | `dictionary<int16, string>` | — | `{NSW1, QLD1, SA1, TAS1, VIC1}`（null: 0） | AEMO NEM 東澳五大調度區代碼（複合主鍵第 1 欄）。 |
| 2 | `timestamp_utc` | `timestamp[ms, tz=UTC]` | UTC 時間 | `1998-12-06 15:00Z` ~ `2026-11-17 13:00Z`（null: 0） | 逐小時區間起點（Interval-Beginning）UTC 時間戳（複合主鍵第 2 欄）。 |
| 3 | `local_date` | `string` | 日期 | `1998-12-07` ~ `2026-11-18`（`YYYY-MM-DD`，null: 0） | 依各州真實民用 IANA 時區換算之當地日曆日期，用於對齊假日與事件表。 |
| 4 | `local_hour` | `int8` | 小時 | `0` ~ `23`（null: 0） | 當地民用時間之小時整數（註：`SA1` 為半小時時區，UTC 整點對應當地 `HH:30`）。 |
| 5 | `day_of_week` | `int8` | 星期 | `1` ~ `7`（ISO-8601：`1`=週一、`7`=週日，null: 0） | 依當地民用時間計算之星期幾。 |
| 6 | `is_weekend` | `int8` | 布林 (0/1) | `{0, 1}`（null: 0） | `day_of_week` 為 `6` 或 `7` 時標記 `1`，否則 `0`。 |
| 7 | `is_dst` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `441,715`，`QLD1` 恆 `0`，null: 0） | 該州於該時刻是否處於當地夏令時間（Daylight Saving Time）。 |
| 8 | `load_mw` | `double` (`float64`) | MW | `-280.12` ~ `14,509.95`（null: `16`） | 電網逐小時平均淨調度負載（`TOTALDEMAND` 算術平均，不含表後屋頂光電；真實缺值保留 `NaN`，負值代表屋頂光電倒灌）。 |
| 9 | `day_type` | `dictionary<int16, string>` | 類別 | `{WEEKDAY, WEEKEND, PUBLIC_HOLIDAY, EMERGENCY_CLOSURE, BOTH}`（null: 0） | 嚴格互斥五分類日型標籤（詳見第 3.3 節）。 |
| 10 | `is_public_holiday` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `36,464`，null: 0） | 該州當地日期是否為靜態法定國定假日（來源：`au_public_holidays.csv`）。 |
| 11 | `is_emergency_closure` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `7,632`，null: 0） | 該州當地日期是否落入重大自然災害／電網事故緊急停班視窗（來源：`au_emergency_closures.csv`）。 |
| 12 | `is_covid_period` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `143,044`，null: 0） | `local_date` 落於 WHO 疫情緊急事件期間 `2020-01-30` ~ `2023-05-05`（含端點）標為 `1`。 |
| 13 | `is_missing` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `16`，null: 0） | 該小時無任何官方原始結算紀錄（`load_mw` 為 `NaN`）時標為 `1`。 |
| 14 | `quality_flag` | `dictionary<int16, string>` | 類別 | `{OK, PARTIAL_HOUR, MISSING}`（null: 0） | 結構性品質摘要旗標（`OK`: `1,168,450`、`PARTIAL_HOUR`: `29`、`MISSING`: `16`）。 |

---

## 2. `full_qc` 完整稽核長表延伸欄位定義（第 15–28 欄）

`AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet` 完整包含上述 14 欄，並附加以下 14 欄供品管稽核與溯源使用：

| # | 欄位名稱 | Parquet 型別 (Arrow) | 物理單位 | 實測值域 / 缺值數 | 業務定義與說明 |
| :-: | :--- | :--- | :---: | :--- | :--- |
| 15 | `iana_tz` | `dictionary<int16, string>` | 時區名稱 | 5 個 IANA 民用時區（null: 0） | `NSW1`: `Australia/Sydney`、`QLD1`: `Australia/Brisbane`、`SA1`: `Australia/Adelaide`、`TAS1`: `Australia/Hobart`、`VIC1`: `Australia/Melbourne`。 |
| 16 | `timestamp_local` | `string` | ISO-8601 | 含冒號偏移字串（如 `1998-12-07T02:00:00+11:00`，null: 0） | 該州當地民用時間完整 ISO-8601 字串（保留 `+10:00`/`+11:00`/`+09:30`/`+10:30`，避免夏令回撥歧義）。 |
| 17 | `raw_interval_min` | `int8` | 分鐘 | `{30, 5}`（null: 0） | 該小時對應之 AEMO 原始結算週期：`2021-09-30 14:00Z` 前為 `30`，之後為 `5`。 |
| 18 | `sample_count` | `int8` | 筆數 | `0`、`1`、`2`、`12`（null: 0） | 該小時內實際彙整之有效原始結算區間筆數（缺值小時為 `0`）。 |
| 19 | `expected_samples` | `int8` | 筆數 | `{2, 12}`（null: 0） | 該小時理論應有之原始區間筆數（30 分鐘時期為 `2`，5 分鐘時期為 `12`）。 |
| 20 | `is_partial_hour` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `29`，null: 0） | 非缺值但實收樣本數不足（`is_missing == 0` 且 `sample_count < expected_samples`）標為 `1`。 |
| 21 | `is_duplicate` | `int8` | 布林 (0/1) | `{0}`（null: 0） | 複合主鍵重複檢核旗標（全庫已驗證為 `0`）。 |
| 22 | `is_dst_transition` | `int8` | 布林 (0/1) | `{0, 1}`（`1`: `211`，null: 0） | 當地 UTC 偏移量較前一小時發生變動（夏令開始或結束切換時刻）標為 `1`。 |
| 23 | `holiday_name` | `dictionary<int16, string>` | 名稱 | 30 種假日名稱（null: `1,132,031`） | 對應 `au_public_holidays.csv` 之法定假日名稱；非假日為 `null`。 |
| 24 | `emergency_event_category` | `dictionary<int16, string>` | 類別 | `{BUSHFIRE, STORM_BLACKOUT, CYCLONE_FLOOD, OTHER_EMERGENCY}`（null: `1,160,863`） | 緊急停班所屬災害大類；非災害日為 `null`。 |
| 25 | `emergency_scope` | `dictionary<int16, string>` | 類別 | `{STATEWIDE, METRO_CAPITAL}`（null: `1,160,863`） | 緊急停班地理影響範圍；非災害日為 `null`。 |
| 26 | `source_file` | `dictionary<int16, string>` | 檔名 | 1,603 份官方月 CSV 檔名（null: `16`） | 該小時所屬之原始月檔名（如 `AU_AEMO_NSW1_RAW_202512.csv`）；缺失小時為 `null`。 |
| 27 | `source_file_sha256` | `dictionary<int16, string>` | Hex 字串 | 64 碼小寫 SHA-256（null: `16`） | 對應 `source_file` 之原始檔指紋；缺失小時為 `null`。 |
| 28 | `version` | `dictionary<int16, string>` | 版本標籤 | `v2.0.0+src.<12>+raw.<12>`（null: 0） | 管線版本與頂層／底稿 SHA-256 複合標籤（完整 64 碼同步寫入 Parquet Schema Metadata）。 |

---

## 3. 下游特徵工程與建模使用規範

### 3.1 主鍵與排序契約
- 進行任何時序運算前，必須確保資料表依 **`["region_id", "timestamp_utc"]` 升冪排序**，且所有 Lag／Rolling／差分操作皆須在 `groupby("region_id")` 邊界內獨立執行，嚴禁跨區串接。
- 切勿使用 `timestamp_local` 或 `(local_date, local_hour)` 作為唯一主鍵（夏令時間結束回撥日會出現重複的當地小時）。

### 3.2 滑動視窗與 Lag 特徵防跨越缺口原則
- 全歷史共有 `16` 筆 `is_missing == 1`（集中於 1999–2001 年四州同步缺漏，`load_mw = NaN`）。
- 計算滯後特徵（如 `lag_1h`、`lag_24h`、`lag_168h`）與滾動統計（如 `rolling_24h_mean`）時，**嚴禁先用 `.dropna()` 壓縮序列再做 `.shift()`**（這會造成時間軸錯位並將相距數小時的觀測值誤當相鄰小時）；正確作法為保持連續 UTC 小時網格做 `.shift()`，再於訓練樣本建構階段丟棄目標值或必要滯後值為 `NaN` 的樣本，確保滑動視窗絕不跨越真實時間缺口。

### 3.3 五分類 `day_type` 與獨立布林旗標搭配建議
- **`day_type`（互斥五分類）**適合樹模型類別特徵或 One-Hot / Embedding 編碼：
  - `BOTH`（`is_emergency_closure=1` & `is_public_holiday=1`）：`168` 小時
  - `EMERGENCY_CLOSURE`（僅緊急停班）：`7,464` 小時
  - `PUBLIC_HOLIDAY`（僅國定假日）：`36,296` 小時
  - `WEEKEND`（非假日且非緊急停班之週末）：`325,335` 小時
  - `WEEKDAY`（一般工作日）：`799,232` 小時
- **獨立布林旗標**（`is_weekend`、`is_public_holiday`、`is_emergency_closure`）適合線性模型或交互項建模（例如同時觀察假日效應與災害效應之疊加）。
- **COVID-19 期間口徑提醒**：於 `2020-01-30 ~ 2023-05-05`（`is_covid_period == 1`，共 `143,044` 小時）內，**`is_public_holiday` 仍照常標記（`5,354` 小時）**，但 **`is_emergency_closure` 刻意維持為 `0`**（維持純自然災害／電網事故口徑，不與疫情封控混雜）；下游訓練若排除疫情期，直接篩選 `is_covid_period == 0` 即可完整切割。
