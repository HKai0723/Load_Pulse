# LoadPulse 澳洲 NEM 災害緊急停班停課事件表完整報告

本報告針對專案外部事件靜態表 `data/external/au_emergency_closures.csv` 進行完整盤點、分類統計、電網物理負載變化對照與國定假日重疊（`BOTH`）專節解析，作為負載預測模型解讀非例行性社會活動停擺與極端災害衝擊之參考基準。

---

## 1. 資料集總覽與收錄原則

- **檔案位置**：`data/external/au_emergency_closures.csv`（最新 SHA-256：`ece7d3be3fc98f3db8f0fdea5c39e5415cbb234e892cc373ce208be0841c3bca`）
- **資料規模**：
  - **總州-日筆數**：**`322`** 筆（唯一複合主鍵 `(region_id, local_date)`，`0` 重複列）
  - **獨立災害事件總數**（依 `holiday_name` 合併去重）：**`44`** 起重大災害／供電緊急事件
  - **涵蓋時間跨度**：`1999-04-14` 至 `2026-11-22`（橫跨 27.6 年；其中 `SA1` 末 4 日 `2026-11-19`–`2026-11-22` 超出目前 AEMO Parquet 末日 `2026-11-17 13:00Z`，保留於事件表供後續補齊原始檔時自動串接）
- **WHO 疫情期間排除原則**：
  - 本表聚焦於**自然災害與電網突發緊急狀態**（林火、風暴停電、氣旋洪災、極端熱浪限電）。於 WHO 國際關注公共衛生緊急事件期間（`2020-01-30` 至 `2023-05-05`），本表刻意維持 **`0` 筆**紀錄，避免將長期疫情封控與短期自然災害混雜；疫情影響統一由主訓練表之獨立旗標 `is_covid_period` 控管。
- **電網負載變動基準線定義**：
  - 下表「平均負載變化幅度（`mean_diff_pct`）」係由 `AU_AEMO_NEM_hourly_1998_2026.parquet` 計算各事件日實際日均負載，與該州**前後 28 天內相同星期幾、且排除所有國定假日與緊急停班日之乾淨平日基準**相比所得之事件期平均變動百分比。

---

## 2. 分類統計摘要

### 2.1 按災害類型（`event_category`）統計

| 災害類型 (`event_category`) | 州-日數 | 州-日占比 | 獨立事件數 | 代表性情境 |
| :--- | :---: | :---: | :---: | :--- |
| **`BUSHFIRE`**（森林大火／火險緊急狀態） | `217` | `67.39%` | `15` | 全州林火緊急狀態／災難狀態、學校預防性停課、大規模撤離 |
| **`STORM_BLACKOUT`**（強風暴／輸配電跳脫停電） | `50` | `15.53%` | `15` | 冰雹／強風毀電塔、跨州聯絡線跳脫、系統孤島化與強制卸載 |
| **`CYCLONE_FLOOD`**（熱帶氣旋／重大洪災） | `49` | `15.22%` | `12` | 氣旋登陸、河道氾濫與都會區疏散停課停運 |
| **`OTHER_EMERGENCY`**（極端熱浪電力短缺減載） | `6` | `1.86%` | `2` | 極端熱浪致尖峰超載，強制工業與數十萬戶輪流限電 |
| **合計** | **`322`** | **`100.00%`** | **`44`** | — |

### 2.2 按調度區（`region_id`）統計

| 調度區 (`region_id`) | 州-日數 | 州-日占比 | 獨立事件數 | 涵蓋小時數 (`is_emergency_closure=1`) | 備註 |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **VIC1**（維多利亞） | `103` | `31.99%` | `10` | `2,472` | 含 2009 黑色星期六（36 日）與 2026 維州林火（30 日） |
| **TAS1**（塔斯馬尼亞） | `78` | `24.22%` | `6` | `1,872` | 含 2018–19 塔州林火（47 日） |
| **SA1**（南澳） | `61` | `18.94%` | `13` | `1,368` | 含 2019–20 袋鼠島林火（23 日）；末 4 日（`2026-11-19..22`）超出現行 Parquet 末日 |
| **QLD1**（昆士蘭） | `45` | `13.98%` | `8` | `1,080` | 以氣旋洪災與 2019 昆士蘭林火（15 日）為主 |
| **NSW1**（新南威爾斯） | `35` | `10.87%` | `7` | `840` | 含 2019–20 黑色夏季三次全州緊急狀態（合計 21 日） |
| **合計** | **`322`** | **`100.00%`** | **`44`** | **`7,632`** | `7,632 = (322 - 4) × 24` 小時 |

### 2.3 按影響範圍（`scope`）統計

| 影響範圍 (`scope`) | 州-日數 | 州-日占比 | 獨立事件數 | 說明 |
| :--- | :---: | :---: | :---: | :--- |
| **`STATEWIDE`** | `302` | `93.79%` | `38` | 全州層級緊急／災難狀態、跨區電網事故或廣泛停課停電 |
| **`METRO_CAPITAL`** | `20` | `6.21%` | `6` | 集中於首府都會區（雪梨、布里斯本、阿得雷德、荷巴特）之停班停課／限電 |
| **合計** | **`322`** | **`100.00%`** | **`44`** | — |

---

## 3. 完整獨立災害事件總目錄（共 44 起，依首次發生日期排序）

| # | 事件名稱 (`holiday_name`) | 州別 | 起訖日期 | 州-日數 | 災害類型 | 範圍 | 含 `BOTH` | 平均負載變化 | 來源網址 |
| :-: | :--- | :---: | :---: | :-: | :---: | :---: | :-: | :---: | :--- |
| 1 | 1999 Sydney Hailstorm | `NSW1` | `1999-04-14` ~ `1999-04-15` | 2 | `STORM_BLACKOUT` | `METRO_CAPITAL` | 否 | `-2.78%` | https://en.wikipedia.org/wiki/1999_Sydney_hailstorm |
| 2 | 2007 Victoria Bushfire Blackout | `VIC1` | `2007-01-16` ~ `2007-01-17` | 2 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `+14.28%` | https://wattclarity.com.au/articles/2007/01/16th-january-2007-bushfires-and-victorias-blackout/ |
| 3 | 2009 Southeastern Australia Heatwave Blackout | `VIC1` | `2009-01-27` ~ `2009-01-30` | 4 | `OTHER_EMERGENCY` | `STATEWIDE` | 否 | `+28.67%` | https://en.wikipedia.org/wiki/2009_southeastern_Australia_heat_wave |
| 4 | 2009 SA Heatwave Load Shedding | `SA1` | `2009-01-29` ~ `2009-01-30` | 2 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `+63.24%` | https://www.aemc.gov.au/sites/default/files/content/0f19c224-5124-4114-b61a-a17f62b1dccb/Final-Report.pdf |
| 5 | 2009 Black Saturday Bushfires | `VIC1` | `2009-02-07` ~ `2009-03-14` | 36 | `BUSHFIRE` | `STATEWIDE` | **是 (1日)** | `-3.12%` | https://en.wikipedia.org/wiki/Black_Saturday_bushfires |
| 6 | 2010 Melbourne Severe Storm | `VIC1` | `2010-03-06` ~ `2010-03-07` | 2 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `-2.48%` | https://knowledge.aidr.org.au/resources/storm-severe-storm-melbourne-victoria-2010/ |
| 7 | September 2010 Victoria Floods | `VIC1` | `2010-09-04` ~ `2010-09-07` | 4 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `+0.38%` | https://en.wikipedia.org/wiki/September_2010_Victoria_floods |
| 8 | 2011 Queensland Floods | `QLD1` | `2011-01-11` ~ `2011-01-14` | 4 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `-4.40%` | https://en.wikipedia.org/wiki/2010%E2%80%932011_Queensland_floods |
| 9 | Cyclone Yasi | `QLD1` | `2011-02-02` ~ `2011-02-03` | 2 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `+2.64%` | https://en.wikipedia.org/wiki/Cyclone_Yasi |
| 10 | 2013 Tasmanian Bushfires | `TAS1` | `2013-01-03` ~ `2013-01-13` | 11 | `BUSHFIRE` | `STATEWIDE` | 否 | `+2.33%` | https://en.wikipedia.org/wiki/2013_Tasmanian_bushfires |
| 11 | Cyclone Oswald Queensland Floods | `QLD1` | `2013-01-29` ~ `2013-01-30` | 2 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `+3.80%` | https://www.qra.qld.gov.au/sites/default/files/2018-10/ceo-monthly-report-february-2013.pdf |
| 12 | 2013 NSW Bushfires State of Emergency | `NSW1` | `2013-10-20` ~ `2013-10-24` | 5 | `BUSHFIRE` | `STATEWIDE` | 否 | `+3.37%` | https://www.theguardian.com/world/2013/oct/23/nsw-bushfires-schools-shut-horror-day |
| 13 | 2015 Sampson Flat Bushfires | `SA1` | `2015-01-02` ~ `2015-01-07` | 6 | `BUSHFIRE` | `METRO_CAPITAL` | 否 | `+34.06%` | https://en.wikipedia.org/wiki/2015_Sampson_Flat_bushfires |
| 14 | 2015 SA Interconnector Trip Blackout | `SA1` | `2015-11-01` ~ `2015-11-01` | 1 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `+1.08%` | https://energycouncil.com.au/south-australia-s-blackouts-not-as-simple-as-it-looks/ |
| 15 | 2015 Pinery Bushfire & School Closures | `SA1` | `2015-11-25` ~ `2015-12-02` | 8 | `BUSHFIRE` | `STATEWIDE` | 否 | `-13.89%` | https://knowledge.aidr.org.au/media/4096/2015-2016-fire-danger-season-pinery-fire-review.pdf |
| 16 | 2016 Tasmanian Floods | `TAS1` | `2016-06-04` ~ `2016-06-09` | 6 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `-0.60%` | https://knowledge.aidr.org.au/resources/flood-tasmania-june-july-2016/ |
| 17 | 2016 SA Statewide Blackout & Floods | `SA1` | `2016-09-28` ~ `2016-09-30` | 3 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `-3.85%` | https://en.wikipedia.org/wiki/2016_South_Australian_blackout |
| 18 | 2016 SA Grid Separation Blackout | `SA1` | `2016-12-01` ~ `2016-12-01` | 1 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `+3.51%` | https://energycouncil.com.au/south-australia-s-blackouts-not-as-simple-as-it-looks/ |
| 19 | 2016 Late December SA Storm Blackouts | `SA1` | `2016-12-27` ~ `2016-12-31` | 5 | `STORM_BLACKOUT` | `STATEWIDE` | **是 (1日)** | `-10.38%` | https://en.wikipedia.org/wiki/2016_South_Australian_blackout |
| 20 | 2017 January SA Storm Blackout | `SA1` | `2017-01-19` ~ `2017-01-20` | 2 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `-7.57%` | https://energycouncil.com.au/south-australia-s-blackouts-not-as-simple-as-it-looks/ |
| 21 | 2017 Adelaide Heatwave Load Shedding | `SA1` | `2017-02-08` ~ `2017-02-08` | 1 | `STORM_BLACKOUT` | `METRO_CAPITAL` | 否 | `+42.61%` | https://en.wikipedia.org/wiki/2016_South_Australian_blackout |
| 22 | Cyclone Debbie | `QLD1` | `2017-03-28` ~ `2017-03-31` | 4 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `-1.30%` | https://www.bom.gov.au/qld/flood/fld_reports/Tropical-Cyclone-Debbie-Technical-Report-Final.pdf |
| 23 | 2018 Hobart Extreme Storm & Floods | `TAS1` | `2018-05-10` ~ `2018-05-11` | 2 | `CYCLONE_FLOOD` | `METRO_CAPITAL` | 否 | `+2.61%` | https://knowledge.aidr.org.au/resources/flood-hobart-flash-flooding-tasmania-2018/ |
| 24 | 2018-19 Tasmanian Bushfires | `TAS1` | `2018-12-28` ~ `2019-02-12` | 47 | `BUSHFIRE` | `STATEWIDE` | **是 (2日)** | `+2.61%` | https://knowledge.aidr.org.au/resources/2018-19-bushfire-tas-tasmanian-bushfires/ |
| 25 | 2019 Victoria Heatwave Load Shedding | `VIC1` | `2019-01-24` ~ `2019-01-25` | 2 | `OTHER_EMERGENCY` | `STATEWIDE` | 否 | `+33.93%` | https://www.aemo.com.au/-/media/files/electricity/nem/market_notices_and_events/power_system_incident_reports/2019/load-shedding-in-vic-on-24-and-25-january-2019.pdf |
| 26 | 2019 Townsville Floods | `QLD1` | `2019-02-01` ~ `2019-02-05` | 5 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `-0.86%` | https://www.theguardian.com/australia-news/2019/feb/01/queensland-floods-man-missing-highway-cut-and-schools-closed |
| 27 | 2019 Queensland Bushfires SoE | `QLD1` | `2019-11-09` ~ `2019-11-23` | 15 | `BUSHFIRE` | `STATEWIDE` | 否 | `-1.11%` | https://www.publications.qld.gov.au/dataset/a989a31f-951d-4ef5-8694-e8fe46ccef09/resource/6452a145-c5d9-4a5f-9889-bcdb92cd26f7/download/12.11.19-78-extra-gazette.pdf |
| 28 | 2019 Black Summer Bushfires SoE 1 | `NSW1` | `2019-11-11` ~ `2019-11-17` | 7 | `BUSHFIRE` | `STATEWIDE` | 否 | `-2.49%` | https://www.environment.nsw.gov.au/topics/air/nsw-air-quality-statements/annual-air-quality-statement-2019/focus-areas/bushfires-2019-air |
| 29 | 2019 SA Catastrophic Fire Danger Closures | `SA1` | `2019-11-20` ~ `2019-11-20` | 1 | `BUSHFIRE` | `STATEWIDE` | 否 | `+40.67%` | https://en.mercopress.com/2019/11/20/australia-lifts-fire-danger-to-catastrophic-and-closes-schools-in-the-southeast |
| 30 | 2019 Black Summer Bushfires SoE 2 | `NSW1` | `2019-12-19` ~ `2019-12-25` | 7 | `BUSHFIRE` | `STATEWIDE` | **是 (1日)** | `-0.62%` | https://www.theguardian.com/australia-news/2020/jan/02/nsw-state-of-emergency-what-does-it-mean-for-the-bushfires-crisis |
| 31 | 2019 Cudlee Creek Bushfire | `SA1` | `2019-12-20` ~ `2019-12-23` | 4 | `BUSHFIRE` | `METRO_CAPITAL` | 否 | `+18.62%` | https://en.wikipedia.org/wiki/2019%E2%80%9320_Australian_bushfire_season |
| 32 | 2019-20 Kangaroo Island Bushfires | `SA1` | `2019-12-30` ~ `2020-01-21` | 23 | `BUSHFIRE` | `STATEWIDE` | **是 (1日)** | `-10.68%` | https://en.wikipedia.org/wiki/2019%E2%80%9320_Australian_bushfire_season |
| 33 | 2020 Victoria Black Summer State of Disaster | `VIC1` | `2020-01-02` ~ `2020-01-11` | 10 | `BUSHFIRE` | `STATEWIDE` | 否 | `-6.13%` | https://www.vpsc.vic.gov.au/state-of-disaster-monitor-advice-and-warnings |
| 34 | 2020 Black Summer Bushfires SoE 3 | `NSW1` | `2020-01-03` ~ `2020-01-09` | 7 | `BUSHFIRE` | `STATEWIDE` | 否 | `+0.29%` | https://en.wikipedia.org/wiki/2019%E2%80%9320_Australian_bushfire_season |
| 35 | Cyclone Jasper | `QLD1` | `2023-12-12` ~ `2023-12-19` | 8 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `+6.61%` | https://www.education.gov.au/early-childhood/announcements/extropical-cyclone-jasper-period-emergency |
| 36 | 2024 Victoria Storm & Tower Collapse Blackout | `VIC1` | `2024-02-13` ~ `2024-02-14` | 2 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `-1.63%` | https://energyproducers.au/news/fact_sheets/victorian-electricity-outage-13-february-2024 |
| 37 | 2024 Tasmania Severe Storms & Blackout | `TAS1` | `2024-08-26` ~ `2024-09-04` | 10 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `+2.55%` | https://alert.tas.gov.au/recovery/incidents/severe-weather-september-2024 |
| 38 | 2024 Victoria Severe Wind & Storm Blackout | `VIC1` | `2024-08-27` ~ `2024-09-06` | 11 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `-4.73%` | https://knowledge.aidr.org.au/resources/storm-severe-wind-and-rainfall-victoria-2024/ |
| 39 | Cyclone Alfred Northern NSW | `NSW1` | `2025-03-05` ~ `2025-03-10` | 4 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `-0.21%` | https://www.nsw.gov.au/ministerial-releases/precautionary-school-closures-northern-nsw-as-tropical-cyclone-alfred-approaches |
| 40 | Cyclone Alfred | `QLD1` | `2025-03-06` ~ `2025-03-10` | 5 | `CYCLONE_FLOOD` | `METRO_CAPITAL` | 否 | `-1.32%` | https://www.theguardian.com/australia-news/2025/mar/05/cyclone-alfred-update-brisbane-schools-and-public-transport-shut-as-queensland-prepares-for-storm-to-hit |
| 41 | 2025 NSW Mid North Coast Floods | `NSW1` | `2025-05-20` ~ `2025-05-22` | 3 | `CYCLONE_FLOOD` | `STATEWIDE` | 否 | `+1.68%` | https://www.theguardian.com/australia-news/2025/may/20/nsw-flash-flooding-floods-weather-newcastle-taree-warnings-school-closures |
| 42 | 2025 Tasmania Severe Wind Blackout | `TAS1` | `2025-10-10` ~ `2025-10-11` | 2 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `+5.54%` | https://www.theguardian.com/australia-news/2025/oct/10/severe-weather-tasmania-wind-fallen-trees-powerlines |
| 43 | 2026 Victoria Bushfires State of Disaster | `VIC1` | `2026-01-10` ~ `2026-02-08` | 30 | `BUSHFIRE` | `STATEWIDE` | **是 (1日)** | `+0.60%` | https://www.premier.vic.gov.au/victorian-government-declares-state-disaster-0 |
| 44 | 2026 SA Eyre Peninsula Supply Emergency | `SA1` | `2026-11-19` ~ `2026-11-22` | 4 | `STORM_BLACKOUT` | `STATEWIDE` | 否 | `N/A`（超出 Parquet 末日） | https://www.energymining.sa.gov.au/consumers/Eyre-Peninsula-and-West-Coast-electricity-supply-emergency |

---

## 4. 國定假日與緊急停班重疊案例專節（`day_type = BOTH`，共 7 州-日 / 168 小時）

當災害緊急狀態橫跨法定國定假日（如聖誕節、元旦、澳洲日或勞動節）時，電網同時承受「假日工商業休假降載」與「災害停電／極端高溫空調暴增」兩種截然不同的疊加效應。因此管線 v2.0 將此 7 州-日獨立劃分為 **`day_type = BOTH`**（並同步維持 `is_public_holiday = 1` 與 `is_emergency_closure = 1`），避免汙染純假日或純平日災害之負載學習曲線：

| # | 調度區 | 當地日期 | 國定假日名稱 (`au_public_holidays.csv`) | 災害事件名稱 (`au_emergency_closures.csv`) | 災害類型 | 日均負載變化 | 日尖峰變化 | 物理成因解讀 |
| :-: | :---: | :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| 1 | `VIC1` | `2009-03-09` | Labour Day | 2009 Black Saturday Bushfires | `BUSHFIRE` | `-12.89%` | `-15.48%` | 勞動節休假疊加林火後撤離與商業活動縮減，全日大幅降載 |
| 2 | `SA1` | `2016-12-27` | Proclamation Day (observed) | 2016 Late December SA Storm Blackouts | `STORM_BLACKOUT` | `-9.72%` | `-13.58%` | 連假補假疊加 15.5 萬戶風暴大停電，雙重拉低淨調度負載 |
| 3 | `TAS1` | `2019-01-01` | New Year's Day | 2018-19 Tasmanian Bushfires | `BUSHFIRE` | `-5.19%` | `-3.28%` | 元旦休假與荷巴特濃煙疏散雙重壓低用電 |
| 4 | `TAS1` | `2019-01-28` | Australia Day | 2018-19 Tasmanian Bushfires | `BUSHFIRE` | `+5.04%` | `+4.93%` | 澳洲日適逢林火高溫乾燥天氣，家戶冷氣負載抵銷休假降載 |
| 5 | `NSW1` | `2019-12-25` | Christmas Day | 2019 Black Summer Bushfires SoE 2 | `BUSHFIRE` | `-16.44%` | `-21.72%` | 聖誕節全州工商業全面停工疊加林火緊急狀態，出現深幅降載 |
| 6 | `SA1` | `2020-01-01` | New Year's Day | 2019-20 Kangaroo Island Bushfires | `BUSHFIRE` | `-31.06%` | `-28.37%` | 元旦休假疊加袋鼠島林火撤離與夏季屋頂光電出力，降幅逾三成 |
| 7 | `VIC1` | `2026-01-26` | Australia Day | 2026 Victoria Bushfires State of Disaster | `BUSHFIRE` | `+1.05%` | `+17.63%` | 澳洲日日間降載但伴隨極端高溫林火，傍晚尖峰反較平日基準飆升 `+17.63%` |

---

## 5. 資料口徑與覆蓋限制說明

1. **事件影響視窗（Impact Window）與地方實際停班停課時點之差異**：
   - 本表所彙整之歷史新聞報導、政府公告與公開百科資料，多係界定重大災害之**整體事件影響視窗（Impact Window）**（例如全州緊急／災難狀態生效期間），與個別地方政府、教育廳或商業機構逐日實際宣布停班停課之起訖時點（如災前預防性提前停課、或災後因電網搶修未完而延長停課）可能存在 1–2 日或區域層級之落差。
   - 因此，建議下游預測模型將 `is_emergency_closure` 與 `day_type`（`EMERGENCY_CLOSURE` / `BOTH`）視為**「災害擾動風險旗標（Disaster Disruption Risk Flag）」**使用，用以提示模型該時段存在顯著非例行用電異常風險，而非假設全州所有工商業負載於標記日內均等幅停擺。
2. **COVID-19 疫情期間（`2020-01-30 ~ 2023-05-05`）刻意排除原則與口徑邊界**：
   - 為維持本事件表「純自然災害與電網事故」之單一口徑，於 WHO 國際關注公共衛生緊急事件期間（`2020-01-30 ~ 2023-05-05`）**刻意不收錄任何疫情封控或緊急停班紀錄（`0` 筆）**。
   - 於主訓練長表中，該疫情期間仍照常保留靜態國定假日標記（`is_public_holiday = 1` 共 `5,354` 小時），並透過獨立旗標 `is_covid_period = 1` 完整區隔。雖然下游模型訓練預期高機率將直接排除此疫情時段，此設計仍能確保兩份外部日曆／事件表之語義邊界清晰、互不混雜，並支援未來進行疫情敏感度或消融驗證。

---

## 6. 下游特徵工程建議
- **事件與溫度交乘**：表列熱浪限電事件（如 2009 SA `+63.24%`、2017 Adelaide `+42.61%`、2019 SA 災難級火險 `+40.67%`）呈現正向極端負載飆升，而風暴斷電／林火聖誕休假則呈現深幅負向降載；建模時建議將 `day_type`（或 `is_emergency_closure`）與氣象溫度／輻照度特徵共同輸入，讓樹模型或神經網路區分「熱浪林火高負載」與「風暴停電低負載」兩類物理型態。
