import pandas as pd

file_path = r"C:\school\Load_Pulse\Denmark\Raw_Consumption_2020_2026.csv"
print("🔍 正在讀取資料，準備開箱...")
df = pd.read_csv(file_path, low_memory=False)

print("\n=== 探索資料的真實面貌 ===")

print("\n1. 我們的地區 (RegionName) 到底有哪幾個？")
print(df['RegionName'].unique())

print("\n2. 用戶分類 (ConsumerCategory3) 到底有哪幾種？")
print(df['ConsumerCategory3'].unique())

print("\n3. 各分類的總筆數分配：")
print(df['ConsumerCategory3'].value_counts())