# LoadPulse — Australia AEMO NEM 全歷史電力負載資料工程管線 (v2.1.0)

> 版本演進與最新異動請參閱 **[CHANGELOG.md](CHANGELOG.md)**。

本專案建構 **LoadPulse** 電力負載預測系統的資料工程與標準化管線，將澳洲能源市場營運商（AEMO）國家電力市場（NEM）五大調度區之長期官方負載資料（完整年份 `1999–2026`，塔州 `2006–2026`），清洗為具備 **統一 UTC 複合主鍵、各州真實民用時區與夏令時間（DST）標記、國定假日優先之純三分類日型與 SHA-256 溯源機制** 的逐小時長表資料集與按年分表 SQLite 資料庫，供後續時間序列預測模型訓練與驗證使用。

---

## 1. 專案範圍與核心資料資產

### 主力資料：澳洲 AEMO NEM 五大調度區（1999–2026）
- **調度區**：`NSW1`（新南威爾斯）、`QLD1`（昆士蘭）、`SA1`（南澳）、`TAS1`（塔斯馬尼亞）、`VIC1`（維多利亞）。
- **完整 UTC 年份邊界與覆蓋範圍**：
  - `NSW1`、`QLD1`、`SA1`、`VIC1`：自完整年份起點 `1999-01-01 00:00:00Z` 至 `2026-11-17 13:00:00Z`（各 `244,382` 小時；已裁切移除 1998 年 12 月非完整週次）。
  - `TAS1`：自併網後首個完整年份起點 `2006-01-01 00:00:00Z` 至 `2026-11-17 13:00:00Z`（`183,014` 小時；已裁切移除 2005 年非完整月份）。
  - `1999–2025` 所有完整 UTC 年份每州皆無時間軸缺口（平年 `8,760` 筆、閏年 `8,784` 筆）；`2026` 年維持最新可用時段不裁切。
- **跨時期取樣頻率演進**：五州同步於 `2021-10-01`（市場時間 AEST）由 **30 分鐘** 結算切換為 **5 分鐘** 結算；管線依分段間隔精準將 Interval-Ending 時間戳平移為 Interval-Beginning 區間起點後逐時平均聚合。

### 處理後主力資料集（`data/processed/`）
| 檔案名稱 | 大小 | 筆數 × 欄數 / 表數 | 用途說明 |
| :--- | :---: | :---: | :--- |
| `AU_AEMO_NEM_raw_1998_2026.parquet` | 28.74 MB | 4,585,729 × 6 | 1,603 份原始月 CSV 無損整合底稿（ZSTD 壓縮，含 `source_file`） |
| `raw_bundle_manifest.json` | 532.92 KB | 1,605 筆來源 | 頂層快篩總指紋 `master_sources_sha256` ＋ 全部來源檔獨立 SHA-256 明細 |
| `AU_AEMO_NEM_hourly_1999_2026.parquet` | 9.37 MB | 1,160,542 × 13 | **主訓練長表**：逐小時淨調度負載、民用時區／DST、純三分類日型與疫情標記 |
| `AU_AEMO_NEM_hourly_1999_2026_full_qc.parquet` | 10.49 MB | 1,160,542 × 25 | **完整稽核長表**：含樣本數、當地 ISO 時間、假日名稱、逐列原始檔 SHA-256 與 `version` |
| `AU_AEMO_NEM_hourly_1999_2026.db` | 371.74 MB | 28 張年表 (`nem_1999`–`nem_2026`) | **按 UTC 年份分表 SQLite 資料庫**：支援標準 SQL 快速查詢（已列 `.gitignore` 本機產出） |

### 外部靜態日曆表（`data/external/`）
- `au_public_holidays.csv`（1,519 筆）：由 `src/data_collection/fetch_au_holidays.py` 產出之各州靜態國定假日表（含法定跨週末補假）。

---

## 2. 主訓練長表規格與 SQLite 年表查詢方式

### 主訓練長表欄位規格（`AU_AEMO_NEM_hourly_1999_2026.parquet`，13 欄）
- **複合主鍵（PK）**：`(region_id, timestamp_utc)`（嚴格唯一，`1,160,542` 筆，`0` 重複）
- **核心欄位**：
  - `region_id`：調度區代號（`NSW1`, `QLD1`, `SA1`, `TAS1`, `VIC1`）
  - `timestamp_utc`：UTC 區間起點時間戳（`timestamp[ms, tz=UTC]`）
  - `local_date`、`local_hour`、`day_of_week`、`is_weekend`：依各州真實民用 IANA 時區換算之當地日期、小時（0–23）、星期（ISO 1–7）與週末旗標（含 `SA1` 半小時時差 `UTC+9:30/+10:30`）
  - `is_dst`：該州該時刻是否處於夏令時間（`1` / `0`，`QLD1` 恆為 `0`）
  - `load_mw`：逐小時平均淨調度負載（MW；不設人為上下限與 IQR 過濾，完整保留如 `SA1` 屋頂太陽能正午倒灌負載現象；真實缺值小時保留 `NaN`）
  - `day_type`：純三分類日型標籤（優先順序 **`PUBLIC_HOLIDAY` > `WEEKEND` > `WEEKDAY`**）：
    - `PUBLIC_HOLIDAY`（`36,158` 小時）：凡 `is_public_holiday == 1`（含週六日國定假日與法定補假）一律歸入此類
    - `WEEKEND`（`325,301` 小時）：非國定假日之週六、週日
    - `WEEKDAY`（`799,083` 小時）：其餘一般工作日
  - `is_public_holiday`、`is_covid_period`（`2020-01-30` ~ `2023-05-05`）、`is_missing`、`quality_flag`（`OK` / `PARTIAL_HOUR` / `MISSING`）

### 按年分表 SQLite 資料庫查詢範例（`AU_AEMO_NEM_hourly_1999_2026.db`）
資料庫內依 UTC 年份拆分為 `nem_1999` 至 `nem_2026` 共 28 張資料表（`1999–2005` 含 4 州、`2006–2026` 含 5 州），每張表均具備 `PRIMARY KEY (region_id, timestamp_utc)` 與 `idx_nem_{YYYY}_region_local_date (region_id, local_date)` 索引：

```sql
-- 查詢 2025 年南澳 (SA1) 國定假日與負淨負載時段
SELECT region_id, timestamp_utc, local_date, local_hour, load_mw, day_type, holiday_name
FROM nem_2025
WHERE region_id = 'SA1' AND load_mw < 0
ORDER BY timestamp_utc;

-- 跨年份合併查詢（如 2024–2025 維州逐時訓練序列）
SELECT region_id, timestamp_utc, load_mw, day_type FROM nem_2024 WHERE region_id = 'VIC1'
UNION ALL
SELECT region_id, timestamp_utc, load_mw, day_type FROM nem_2025 WHERE region_id = 'VIC1'
ORDER BY timestamp_utc;
```

---

## 3. 目錄結構與技術報告

```text
Load_Pulse/
├── archive/                        # 封存舊期多國資料、2021-01 試跑產出與拆分原始檔（不上 Git）
├── data/
│   ├── external/                   # 靜態國定假日表與歷史事件參考檔
│   ├── processed/                  # 原始整合 Parquet、SHA-256 總清單、1999–2026 雙 Parquet 與 SQLite 年表庫
│   └── raw/Australia_AEMO/         # 唯讀官方原始月 CSV 與 raw_manifest.json（不上 Git）
├── data_pipeline/
│   ├── build_raw_parquet.py        # 1,603 原始 CSV 無損打包與 1,605 檔 SHA-256 總清單產生器
│   ├── core_pipeline.py            # 核心向量化清洗與 SQLite 分表函式庫 (PIPELINE_VERSION = "2.1.0")
│   └── run_australia_pipeline.py   # 澳洲 1999–2026 長表清洗、雙 Parquet 與 SQLite 建庫入口
├── outputs/figures/                # 資料品質、熱圖、日型對比與地理分佈圖
├── reports/
│   ├── au_data_quality_report.md                   # 資料品質檢核報告
│   ├── au_emergency_closures_report.md             # 歷史災害事件盤點參考報告
│   ├── coverage_report.md                          # 五州資料覆蓋跨度與候選時序切分參考方案
│   ├── data_dictionary.md                          # 主訓練長表 (13 欄)、稽核長表 (25 欄) 與 SQLite 資料字典
│   ├── data_quality_spec.md                        # 管線核心功能拆解、品質規格與 SHA-256 說明
│   ├── data_source_review.md                       # 跨國電網選材物理評估、官方授權與待確認口徑清單
│   ├── pipeline_v2_release_notes.md                # 管線架構演進說明
│   ├── statistical_potential_and_anomalies_report.md # WP2/WP3 統計結構斷裂與殘差潛能探勘報告
│   └── timestamp_availability.md                   # 時間戳發布可得性、氣象待接通缺口與特殊時間轉折點
├── src/
│   ├── data_collection/            # AEMO 原始檔下載、國定假日產生與檢核腳本
│   └── visualization/              # 檢核圖表與 Cartopy 調度區地圖繪製腳本
├── wa_wem_pilot/                   # 西澳 WEM 獨立實驗目錄
├── .gitignore
├── CHANGELOG.md                    # 中文版本變更紀錄
└── README.md
```
