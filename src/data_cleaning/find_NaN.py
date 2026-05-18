import pandas as pd
import os

# 1. 設定路徑
file_path = r"C:\school\Load_Pulse\Denmark\Raw_Consumption_2020_2026.csv"

# 2. 讀取資料
# 這裡加一個 low_memory=False 是因為五年的資料很大，讓 Pandas 處理起來更穩定
print("🔍 正在讀取資料檔案...")
df = pd.read_csv(file_path, low_memory=False)

# 3. 檢查基本資訊
print(f"📊 資料讀取完成！總共有 {len(df)} 筆資料。")

# 4. 抓出缺漏值 (Missing Values)
# isnull() 會把有資料的地方標成 False，沒資料的地方標成 True
# sum() 則會把所有的 True 加起來，得出每一欄的缺漏總數
missing_summary = df.isnull().sum()

print("\n--- 各欄位缺漏值統計 ---")
print(missing_summary)

# 5. 進階檢查：看看缺漏值長什麼樣子
# 如果有任何一欄有缺漏值，我們就把那些缺漏的資料行「抓出來看一眼」
if missing_summary.sum() > 0:
    print("\n⚠️ 發現缺漏值！以下是前幾筆含有缺漏值的資料：")
    # 抓出只要「任何一欄」有空值的資料行
    rows_with_nan = df[df.isnull().any(axis=1)]
    print(rows_with_nan.head())
else:
    print("\n✅ 太棒了！這份資料在技術上沒有任何空值 (NaN)。")
