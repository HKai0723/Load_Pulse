import pandas as pd
from pathlib import Path

# ==========================================
# 1. 路徑設定
# ==========================================
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
parquet_dir = project_root / "Denmark_weather" / "Weather_Regional_Split"

# 🌟 鎖定慣犯：請確認截圖中那顆深紅色的 ID 是不是 04271
TARGET_STATION = "04271" 

output_csv = current_dir / f"station_{TARGET_STATION}_5years_raw.csv"

print(f"🔍 啟動【五年期】全境搜索：全面盤查測站 {TARGET_STATION} (2021-2025)...")

# ==========================================
# 2. 一口氣掃描五年份的 Parquet 檔案
# ==========================================
parquet_files = list(parquet_dir.glob("Weather_20*.parquet"))
found_data = []

for file_path in parquet_files:
    df = pd.read_parquet(file_path, columns=['observed_time', 'station_id', 'parameter_id', 'value'])
    df['safe_id'] = df['station_id'].astype(str).str.zfill(5)
    
    # 篩選條件：特定測站 + 乾球溫度
    df_filtered = df[(df['safe_id'] == TARGET_STATION) & (df['parameter_id'] == 'temp_dry')].copy()
    
    if not df_filtered.empty:
        found_data.append(df_filtered)

# ==========================================
# 3. 顯示結果：看看這台暖氣吹了多久
# ==========================================
if found_data:
    df_final = pd.concat(found_data, ignore_index=True)
    df_final['observed_time'] = pd.to_datetime(df_final['observed_time'])
    
    # 🌟 這裡開始加入「時間軸重塑」魔法 🌟
    print("⏳ 正在重建連續時間軸，讓隱形斷層現形...")
    
    # 先把時間設為索引，方便重塑
    df_final = df_final.set_index('observed_time').sort_index()
    
# 建立一條「每 1 小時一格」的完美連續時間軸
    full_time_range = pd.date_range(
        start=df_final.index.min(), 
        end=df_final.index.max(), 
        freq='1h'  # ✨ 這裡請改成小寫 h
    )
    
    # 執行對齊 (Reindex)，沒資料的小時會自動填入 NaN
    df_continuous = df_final.reindex(full_time_range)
    
    # 補回被 reindex 沖掉的固定資訊 (station_id 和 parameter_id)
    # 這樣 Excel 裡每一行才會有 ID
    df_continuous['station_id'] = TARGET_STATION
    df_continuous['parameter_id'] = 'temp_dry'
    
    # 把時間索引轉回普通欄位，方便存檔
    df_continuous = df_continuous.reset_index().rename(columns={'index': 'observed_time'})
    
    print(f"\n✅ 盤查與重塑完畢！五年連續時間軸共 {len(df_continuous):,} 筆觀測位置。")
    
    # 顯示最熱的資料 (這裡依然可以看到那 21.7 度的壞蛋)
    print("\n🔥 該測站五年內『最熱』的 20 筆資料：")
    print(df_continuous.sort_values(by='value', ascending=False).head(20).to_string(index=False))
    
    # 🌟 匯出這個「帶有斷層」的連續資料
    df_continuous.to_csv(output_csv, index=False)
    
    print(f"\n💾 完美的『連續時間軸』原始資料已匯出至：{output_csv}")
    print("👉 現在去 Excel 畫圖，你會看到那些『壞過年』的月份會直接斷掉，這才是真實情況！")
else:
    print("👻 找不到該測站的資料。")