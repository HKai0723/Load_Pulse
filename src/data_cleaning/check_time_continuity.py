import pandas as pd
import os

# 1. 設定你的目標檔案路徑 (這次是 CSV，不是 DB)
csv_path = r"C:\school\Load_Pulse\Denmark\Clean_Consumption_Wide.csv"
# 確保時間欄位的名稱正確，根據你之前轉換的結果，通常是 'TimeUTC'
time_col = "TimeUTC"

def check_time_gaps_csv(file_path, time_col):
    if not os.path.exists(file_path):
        print(f"❌ 找不到檔案：{file_path}")
        return

    try:
        print(f"🔌 正在讀取檔案：{file_path}...")
        # 為了節省記憶體，我們只讀取時間這一個欄位
        df = pd.read_csv(file_path, usecols=[time_col])

        # 2. 將字串轉換為 Pandas 的 datetime 格式
        print("⏳ 正在轉換時間格式並檢查排序...")
        df[time_col] = pd.to_datetime(df[time_col])
        
        # 移除重複值並確保按時間排序
        df = df.sort_values(by=time_col).drop_duplicates().reset_index(drop=True)

        # 3. 找出起始與結束時間
        start_time = df[time_col].min()
        end_time = df[time_col].max()
        
        print(f"\n📅 資料涵蓋範圍：")
        print(f"   起始時間：{start_time}")
        print(f"   結束時間：{end_time}")

        # 4. 產生標準的「每小時」時間軸
        # 假設資料是每小時一筆 (freq='h')
        expected_times = pd.date_range(start=start_time, end=end_time, freq='h')
        
        actual_count = len(df)
        expected_count = len(expected_times)
        missing_count = expected_count - actual_count

        print(f"\n📊 完整性報告：")
        print(f"   預期資料筆數 (無斷層)：{expected_count:,} 筆")
        print(f"   實際擁有筆數：{actual_count:,} 筆")

        # 5. 判斷是否有時間破洞
        if missing_count == 0:
            print("   ✨ 結論：太完美了！時間軸完全連續，沒有任何斷層。")
        else:
            print(f"   ⚠️ 結論：發現 {missing_count:,} 個時間斷層 (缺失的整點資料)！")
            
            # 使用集合相減找出缺失的時間
            missing_timestamps = set(expected_times) - set(df[time_col])
            missing_sorted = sorted(list(missing_timestamps))
            
            print("\n🔍 以下是消失的前 10 個時間斷層：")
            for t in missing_sorted[:10]:
                print(f"   - {t}")
                
            if missing_count > 10:
                print(f"   ... (還有 {missing_count - 10} 個斷層未列出)")

    except Exception as e:
        print(f"\n❌ 處理過程中發生錯誤：{e}")

# 執行檢查
if __name__ == "__main__":
    check_time_gaps_csv(csv_path, time_col)