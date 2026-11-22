# LoadPulse — Australia AEMO NEM 電力負載資料工程管線

本專案建構 **LoadPulse** 電力負載預測系統的資料工程與標準化管線，將澳洲能源市場營運商（AEMO）國家電力市場（NEM）五大調度區之歷史負載資料，整理為具備統一時間戳主鍵、標準物理單位（MW）、品質旗標與外部日曆／事件特徵的時間序列資料集，供後續機器學習／深度學習模型訓練與驗證使用。

## 1. 專案範圍與資料資產

### 主力資料：澳洲 AEMO NEM 五大調度區（1998–2026）
- **調度區**：`NSW1`、`QLD1`、`SA1`、`TAS1`、`VIC1`（不含西澳 WEM 與北領地）。
- **原始資料目錄**：`data/raw/Australia_AEMO/{REGION}/`（共 1,603 份月度 CSV 與 `raw_manifest.json` 完整性／SHA-256 清單，請維持唯讀，勿直接修改）。
  - `NSW1`、`QLD1`、`SA1`、`VIC1`：各 336 檔，涵蓋 `1998-12` 至 `2026-11`（首月 `199812` 與末月 `202611` 為非完整月截斷）。
  - `TAS1`：259 檔，自 `2005-05` 併網起算至 `2026-11`（`199812–200504` 為官方 404）。
- **原始欄位與頻率演進**：
  - 欄位：`REGION,SETTLEMENTDATE,TOTALDEMAND,RRP,PERIODTYPE`（`TOTALDEMAND` 為淨調度負載 MW，`SETTLEMENTDATE` 為 Interval-Ending 市場時間）。
  - 取樣間隔：五州同步於 `2021-10-01` 由 **30 分鐘** 切換為 **5 分鐘**；時間字串格式隨歷史區間演進（含／無雙引號、含／無秒數），合併與轉區間起點時須依各段間隔正確處理。

### 外部日曆與事件靜態表（`data/external/`）
- `au_public_holidays.csv`：由 `src/data_collection/fetch_au_holidays.py`（基於 `holidays` 套件）產出之靜態國定假日表。
- `au_emergency_closures.csv`：由原始分區緊急停班 CSV 合併去重整理而成（已刻意排除 `2020-01-30` 至 `2023-05-05` 疫情期間事件）。
- 原始兩份拆分緊急停班檔、早期 2021-01 測試產出、丹麥／美國舊資料與腳本皆已封存至 `archive/`。

## 2. 目錄結構

```text
Load_Pulse/
├── archive/                  # 封存舊期多國資料、2021-01 試跑產出、舊腳本與拆分原始檔
├── data/
│   ├── external/             # 靜態國定假日表與合併後緊急停班事件表
│   ├── processed/            # 洗好與整合後的標準化資料輸出（如 .parquet / 抽樣檔）
│   └── raw/Australia_AEMO/   # 唯讀原始月度 CSV 與 raw_manifest.json
├── data_pipeline/            # 核心清洗函式庫 (core_pipeline.py) 與管線入口
├── outputs/figures/          # 檢核圖表輸出
├── reports/                  # 資料來源評估與品質檢核報告
├── src/
│   ├── data_collection/      # AEMO 擷取與靜態國定假日產生腳本
│   └── visualization/        # 品質報表與區域地圖繪製腳本
├── .gitignore
└── README.md