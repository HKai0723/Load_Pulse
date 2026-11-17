# LoadPulse — 跨國電力負載資料工程與標準化管線

本專案為 **LoadPulse** 電力負載預測系統之資料工程模組，負責從官方電力調度機構擷取原始負載資料，並透過模組化清洗管線轉換為具備統一 UTC 時間軸、標準物理單位（MW）與完整品質旗標（Quality Flags）之逐小時時間序列資料集。

## 專案目錄結構

```text
Load_Pulse/
├── data/
│   ├── raw/                                # 各國官方未加工原始資料（唯讀保存，絕不覆寫）
│   │   ├── Australia_AEMO/                 # 澳洲國家電力市場 (NEM 五大調度區)
│   │   ├── Denmark_Energinet/              # 丹麥輸電系統調度中心 (Energinet)
│   │   └── US_EIA_Demand/                  # 美國聯邦能源資訊署 (EIA 次平衡區)
│   └── processed/                          # 清洗後之標準化輸出資料
│       ├── pilot_load_hourly.csv                   # 丹麥標準 7 欄位逐時 Pilot 檔
│       ├── DK_load_hourly_202101_full_qc.csv       # 丹麥完整品質旗標與溯源檢核檔
│       ├── AU_AEMO_NEM_hourly_202101.csv           # 澳洲五大調度區逐時統一寬表 (PK: timestamp_utc)
│       ├── AU_AEMO_NEM_hourly_202101_full_qc.csv   # 澳洲完整品質旗標與溯源檢核寬表
│       ├── US_EIA_ALL_hourly_202101.csv            # 美國八大調度區逐時統一寬表 (PK: timestamp_utc)
│       └── US_EIA_ALL_hourly_202101_full_qc.csv    # 美國完整品質旗標與溯源檢核寬表
├── data_pipeline/                          # 核心資料清洗與標準化管線
│   ├── core_pipeline.py                    # 通用 10 項標準化清洗與品質檢核函式
│   ├── run_denmark_pipeline.py             # 丹麥資料前處理與管線執行入口
│   ├── run_australia_pipeline.py           # 澳洲五大調度區前處理與寬表整合入口
│   └── run_us_eia_pipeline.py              # 美國 EIA 八大調度區前處理與寬表整合入口
├── src/
│   ├── data_collection/                    # 各國原始資料獨立擷取腳本
│   │   ├── fetch_denmark.py
│   │   ├── fetch_australia.py
│   │   └── fetch_us_eia.py
│   └── visualization/                      # 品質檢核與空間分布視覺化腳本
│       ├── plot_quality_report.py
│       └── plot_region_maps.py
├── outputs/
│   └── figures/                            # 品質檢核與空間分布圖表 (.png)
├── reports/                                # 工程評估與品質檢核報告
│   ├── data_source_review.md               # 跨國資料來源調查與選定評估報告
│   ├── dk_data_quality_report.md           # 丹麥資料品質檢核報告
│   ├── au_data_quality_report.md           # 澳洲 AEMO NEM 資料品質檢核報告
│   └── us_data_quality_report.md           # 美國聯邦 EIA 資料品質檢核報告
├── .env                                    # 本機 API 金鑰設定（已列入 .gitignore，不上傳）
└── .gitignore