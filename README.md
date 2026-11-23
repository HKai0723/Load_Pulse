# LoadPulse — Australia AEMO NEM 全歷史電力負載資料工程管線 (v2.0.0)

本專案建構 **LoadPulse** 電力負載預測系統的資料工程與標準化管線，將澳洲能源市場營運商（AEMO）國家電力市場（NEM）五大調度區之全歷史官方負載資料（`1998-12` 至 `2026-11`），清洗為具備 **統一 UTC 複合主鍵、各州真實民用時區與夏令時間（DST）標記、五分類日型／災害事件特徵與三層 SHA-256 溯源機制** 的逐小時長表資料集，供後續機器學習／深度學習負載預測模型訓練與驗證使用。

---

## 1. 專案範圍與核心資料資產

### 主力資料：澳洲 AEMO NEM 五大調度區（1998–2026）
- **調度區**：`NSW1`（新南威爾斯）、`QLD1`（昆士蘭）、`SA1`（南澳）、`TAS1`（塔斯馬尼亞）、`VIC1`（維多利亞）；不含獨立運作之西澳 WEM 與北領地。
- **時間覆蓋與併網邊界**：
  - `NSW1`、`QLD1`、`SA1`、`VIC1`：涵蓋 `1998-12-06 15:00Z` 至 `2026-11-17 13:00Z`（各 244,991 小時；首月 `199812` 與末月 `202611` 為非完整月截斷）。
  - `TAS1`：自 `2005-05-16 03:00Z` 併入 NEM 起算至 `2026-11-17 13:00Z`（188,531 小時；`199812–200504` 為官方未併網 404）。
- **跨時期取樣頻率演進**：五州同步於 `2021-10-01`（市場時間 AEST）由 **30 分鐘** 結算切換為 **5 分鐘** 結算；管線依分段間隔精準將 Interval-Ending 時間戳平移為 Interval-Beginning 區間起點後逐時平均聚合。

### 處理後主力資料集（`data/processed/`）
| 檔案名稱 | 大小 | 筆數 × 欄數 | 用途說明 |
| :--- | :---: | :---: | :--- |
| `AU_AEMO_NEM_raw_1998_2026.parquet` | 28.74 MB | 4,585,729 × 6 | 1,603 份原始月 CSV 無損整合底稿（ZSTD 壓縮，含 `source_file`） |
| `raw_bundle_manifest.json` | 532.92 KB | 1,605 筆來源 | 頂層快篩總指紋 `master_sources_sha256` ＋ 全部 1,605 檔獨立 SHA-256 明細 |
| `AU_AEMO_NEM_hourly_1998_2026.parquet` | 9.51 MB | 1,168,495 × 14 | **主訓練長表**：逐小時淨調度負載、民用時區／DST、五分類日型與疫情標記 |
| `AU_AEMO_NEM_hourly_1998_2026_full_qc.parquet` | 10.65 MB | 1,168,495 × 28 | **完整稽核長表**：含樣本數、當地 ISO 時間、事件明細、逐列原始檔 SHA-256 與 `version` |

### 外部靜態日曆與事件表（`data/external/`）
- `au_public_holidays.csv`（1,519 筆）：由 `src/data_collection/fetch_au_holidays.py` 產出之各州靜態國定假日表。
- `au_emergency_closures.csv`（322 州-日 / 44 起獨立重大災害事件）：涵蓋林火、風暴停電、氣旋洪患等重大緊急停班停課事件，已刻意排除 `2020-01-30` 至 `2023-05-05` WHO COVID-19 疫情期間（該期間改由主表 `is_covid_period` 獨立標記）。

---

## 2. 主訓練長表欄位規格（`AU_AEMO_NEM_hourly_1998_2026.parquet`）

- **複合主鍵（PK）**：`(region_id, timestamp_utc)`（嚴格唯一，1,168,495 筆，0 重複）
- **核心欄位**：
  - `region_id`：調度區代號（`NSW1`, `QLD1`, `SA1`, `TAS1`, `VIC1`）
  - `timestamp_utc`：UTC 區間起點時間戳（`timestamp[s, UTC]`）
  - `local_date`、`local_hour`、`day_of_week`、`is_weekend`：依各州真實民用 IANA 時區換算之當地日期、小時（0–23）、星期（ISO 1–7）與週末旗標（含 `SA1` 半小時時差 `UTC+9:30/+10:30`）
  - `is_dst`：該州該時刻是否處於夏令時間（`1` / `0`，`QLD1` 恆為 `0`）
  - `load_mw`：逐小時平均淨調度負載（MW；不設人為上下限與 IQR 過濾，完整保留如 `SA1` 屋頂太陽能正午倒灌負載現象；真實缺值小時保留 `NaN`）
  - `day_type`：互斥五分類日型標籤：
    - `BOTH`（168 小時）：同時為緊急停班與國定假日
    - `EMERGENCY_CLOSURE`（7,464 小時）：僅緊急停班災害日
    - `PUBLIC_HOLIDAY`（36,296 小時）：僅國定假日
    - `WEEKEND`（325,335 小時）：一般週末（週六、日）
    - `WEEKDAY`（799,232 小時）：一般工作日
  - `is_public_holiday`、`is_emergency_closure`、`is_covid_period`（`2020-01-30` ~ `2023-05-05`）、`is_missing`、`quality_flag`（`OK` / `PARTIAL_HOUR` / `MISSING`）

---

## 3. 目錄結構與技術報告

```text
Load_Pulse/
├── archive/                        # 封存舊期多國資料、2021-01 試跑產出與拆分原始檔（不上 Git）
├── data/
│   ├── external/                   # 靜態國定假日表與合併緊急停班事件表
│   ├── processed/                  # 原始整合 Parquet、SHA-256 總清單與清洗後雙 Parquet
│   └── raw/Australia_AEMO/         # 唯讀官方原始月 CSV 與 raw_manifest.json（不上 Git）
├── data_pipeline/
│   ├── build_raw_parquet.py        # 1,603 原始 CSV 無損打包與 1,605 檔 SHA-256 總清單產生器
│   ├── core_pipeline.py            # 核心向量化清洗函式庫 (PIPELINE_VERSION = "2.0.0")
│   └── run_australia_pipeline.py   # 澳洲全歷史長表清洗與雙 Parquet 輸出入口
├── outputs/figures/                # 全歷史資料品質、熱圖、事件對比與地理分佈圖
├── reports/
│   ├── au_data_quality_report.md       # 1998–2026 全歷史資料品質檢核報告
│   ├── au_emergency_closures_report.md # 澳洲 44 起重大緊急停班災害事件完整目錄與統計
│   ├── coverage_report.md              # 五州資料覆蓋跨度與 3 套候選時序切分參考方案
│   ├── data_dictionary.md              # 主訓練長表 (14 欄) 與稽核長表 (28 欄) 獨立資料字典
│   ├── data_quality_spec.md            # 管線 10 大功能拆解、品質規格與三層 SHA-256 說明
│   ├── data_source_review.md           # 跨國電網選材物理評估、官方授權與待確認口徑清單
│   ├── pipeline_v2_release_notes.md    # 管線 Ver 2.0 vs Ver 1.0 架構演進與差異說明
│   └── timestamp_availability.md       # 時間戳發布可得性、氣象待接通缺口與 6 大時間轉折點
├── src/
│   ├── data_collection/            # AEMO 原始檔下載、國定假日產生與緊急停班驗證腳本
│   └── visualization/              # 全歷史檢核圖表與 Cartopy 調度區地圖繪製腳本
├── .gitignore
└── README.md