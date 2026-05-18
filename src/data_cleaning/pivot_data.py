import pandas as pd
import os

# 1. 讀取我們那份完美無瑕的原始資料
file_path = r"C:\school\Load_Pulse\Denmark\Raw_Consumption_2020_2026.csv"
save_path = r"C:\school\Load_Pulse\Denmark\Clean_Consumption_Wide.csv"

print("🔄 正在讀取資料，準備進行 Pivot 轉換...")
df = pd.read_csv(file_path, low_memory=False)

# 2. 進行 Pivot (樞紐分析)
# index: 我們要保留為每一列唯一標籤的欄位
# columns: 我們要把哪個欄位裡面的「值」攤開變成「新欄位」
# values: 新欄位裡面要填入什麼數字
df_wide = df.pivot_table(
    index=['TimeUTC', 'RegionName'], 
    columns='ConsumerCategory3', 
    values='ConsumptionkWh'
).reset_index()

# 3. 重新命名欄位 (把丹麥文轉成直覺的英文)
# df_wide.columns.name = None 是為了把原本 columns 的標籤清掉，讓表格更乾淨
df_wide.columns.name = None
df_wide = df_wide.rename(columns={
    'Privat': 'load_private',
    'Erhverv': 'load_business',
    'Offentlige foretagender': 'load_public'
})

# 4. 存檔
df_wide.to_csv(save_path, index=False, encoding='utf-8-sig')

print(f"\n✅ 轉換成功！原本的 65 萬筆資料，已經濃縮合併成 {len(df_wide)} 筆寬表格資料。")
print(f"📂 乾淨的寬表格已存至：{save_path}")

# 偷看一下結果
print("\n👀 轉換後的前五筆資料長這樣：")
print(df_wide.head())