import pandas as pd
import os

# 1. 設定路徑
file_path = r"C:\school\Load_Pulse\Denmark\Raw_Consumption_2020_2026.csv"
log_path = r"C:\school\Load_Pulse\Denmark\privacy_trigger_log.txt"

print("🔍 正在加載資料並進行隱私保護偵測...")
df = pd.read_csv(file_path, low_memory=False)

# 2. 核心邏輯：計算每個「時間 + 地區」組合中，出現了多少種 ConsumerCategory3
# groupby 就像是 Excel 的樞紐分析，把相同時間、地區的人聚在一起
# .size() 會計算每一組有多少筆資料
check_df = df.groupby(['TimeUTC', 'RegionName']).size().reset_index(name='CategoryCount')

# 3. 定義什麼叫「異常」
# 根據資料特性，正常應該有 3 個分類。如果少於 3 個，就是觸發了合併機制
anomalies = check_df[check_df['CategoryCount'] < 3]

# 4. 準備寫入 Log 檔
print(f"⚠️ 偵測完成！共發現 {len(anomalies)} 個時段疑似觸發隱私保護機制。")

with open(log_path, 'w', encoding='utf-8') as f:
    f.write("=== Load_Pulse 專案：20/60 隱私保護觸發紀錄 (Log) ===\n")
    f.write(f"檢測檔案: {os.path.basename(file_path)}\n")
    f.write(f"總資料列數: {len(df)}\n")
    f.write("-" * 50 + "\n\n")
    
    if len(anomalies) > 0:
        for index, row in anomalies.iterrows():
            time = row['TimeUTC']
            region = row['RegionName']
            count = row['CategoryCount']
            
            # 找出那一組到底剩下了哪幾個分類，這樣我們就知道誰消失了
            remaining_categories = df[(df['TimeUTC'] == time) & (df['RegionName'] == region)]['ConsumerCategory3'].tolist()
            
            log_msg = f"[警示] 時間: {time} | 地區: {region} | 剩餘分類數: {count} | 存在分類: {remaining_categories}\n"
            f.write(log_msg)
    else:
        f.write("恭喜！在目前資料集中未發現明顯的隱私合併跡象。\n")

print(f"✅ Log 檔案已生成：{log_path}")