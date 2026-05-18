import requests
import pandas as pd
import os
import time

# 1. 設定工作目錄與輸出檔名
save_dir = r"C:\school\Load_Pulse\Denmark"
if not os.path.exists(save_dir):
    os.makedirs(save_dir)
    
file_path = os.path.join(save_dir, "Raw_Consumption_2020_2026.csv")
url = 'https://api.energidataservice.dk/dataset/ConsumptionConsumerCategoryHour'

# 2. 精準控制時間區間 (資工實用技巧：List 串接)
# 我們先用 pd.date_range 產生 2021-01-01 到 2026-01-01 每個月的第一天
middle_dates = [d.strftime('%Y-%m-%dT00:00') for d in pd.date_range(start='2021-01-01', end='2026-01-01', freq='MS')]

# 然後把你要的 2020-12-31 裝在最前面，把包辦 1/1 的 2026-01-02 裝在最後面
date_list = ["2020-12-31T00:00"] + middle_dates + ["2026-01-02T00:00"]

print(f"🚀 開始按月抓取資料，總範圍：{date_list[0]} 至 {date_list[-1]} ...")

# 3. 逐區間抓取
for i in range(len(date_list) - 1):
    start_date = date_list[i]
    end_date = date_list[i+1]
    
    print(f"📅 正在抓取: {start_date} 至 {end_date}...")
    
    params = {
        'start': start_date,
        'end': end_date,
        'limit': 100000  # 單月資料量不會超過 10 萬，這樣設很安全
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json().get('records', [])
        
        if data:
            df_month = pd.DataFrame(data)
            
            # 對單月資料做正向排序 (由舊到新)
            if 'HourUTC' in df_month.columns:
                df_month = df_month.sort_values('HourUTC')
            elif 'TimeUTC' in df_month.columns:
                df_month = df_month.sort_values('TimeUTC')
            
            # 寫入 CSV (第一筆寫入標題，後續只追加內容)
            is_first_chunk = not os.path.exists(file_path)
            df_month.to_csv(file_path, mode='a', index=False, 
                            header=is_first_chunk, encoding='utf-8-sig')
            
        # 休息 0.5 秒避免被 API 阻擋
        time.sleep(0.5)
        
    except Exception as e:
        print(f"❌ 抓取 {start_date} 時發生錯誤: {e}")

print(f"\n🎉 任務完成！完美的排序資料已存入：{file_path}")