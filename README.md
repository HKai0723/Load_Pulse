# LoadPulse — 跨國電力負載資料工程與標準化管線

本專案為 **LoadPulse** 電力負載預測系統之資料工程模組，負責從官方電力調度機構擷取原始負載資料，並透過模組化清洗管線轉換為具備統一 UTC 時間軸、標準物理單位（MW）與完整品質旗標（Quality Flags）之逐小時時間序列資料集。

## 專案目錄結構

```text
Load_Pulse/
├── data/
│   ├── raw/                        # 各國官方未加工原始資料（唯讀保存，絕不覆寫）
│   │   ├── Australia_AEMO/         # 澳洲國家電力市場 (NEM 五大調度區)
│   │   ├── Denmark_Energinet/      # 丹麥輸電系統調度中心 (Energinet)
│   │   └── US_EIA_Demand/          # 美國聯邦能源資訊署 (EIA 次平衡區)
│   └── processed/                  # 清洗後之標準化輸出資料
│       ├── pilot_load_hourly.csv               # 標準 7 欄位逐時 Pilot 檔（供建模組使用）
│       └── DK_load_hourly_202101_full_qc.csv   # 含完整品質旗標與溯源欄位之檢核檔
├── data_pipeline/                  # 核心清洗與視覺化管線
│   ├── core_pipeline.py            # 通用 10 項標準化清洗與品質檢核函式
│   ├── run_denmark_pipeline.py     # 丹麥資料前處理與管線執行入口
│   └── plot_quality_report.py      # 品質報告圖表自動繪製腳本
├── src/
│   └── data_collection/            # 各國原始資料獨立擷取腳本
│       ├── fetch_denmark.py
│       ├── fetch_australia.py
│       └── fetch_us_eia.py
├── outputs/
│   └── figures/                    # 品質檢核視覺化圖表 (.png)
├── reports/                        # 工程評估與品質檢核報告
│   ├── data_source_review.md       # 跨國資料來源調查與選定評估報告
│   └── data_quality_report.md      # 資料清洗品質體檢報告
├── .env                            # 本機 API 金鑰設定
└── .gitignore