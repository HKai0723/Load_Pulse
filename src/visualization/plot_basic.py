import pandas as pd
import matplotlib.pyplot as plt

# 1. 讀取我們洗好的乾淨資料
file_path = r"C:\school\Load_Pulse\Denmark\Clean_Consumption_Wide.csv"
print("📊 正在讀取資料...")
df = pd.read_csv(file_path)

# 2. 計算總用電量
# 我們把三個分類 (住宅、商業、公共) 加起來，新增一個叫做 'Total_Load' 的欄位
df['Total_Load'] = df['load_private'] + df['load_business'] + df['load_public']

# 依照地區 (RegionName) 分組，把這五年的 'Total_Load' 全部加總，並由大排到小
region_sum = df.groupby('RegionName')['Total_Load'].sum().sort_values(ascending=False)

# --- 開始畫圖 ---
print("🎨 正在繪製長條圖...")
# 設定畫布大小 (寬10, 高6)
plt.figure(figsize=(10, 6))

# 畫出長條圖，並給它漂亮的顏色
colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
region_sum.plot(kind='bar', color=colors)

# 設定標題與軸標籤
plt.title('Denmark 2021-2025 Total Electricity Consumption by Region', fontsize=16)
plt.xlabel('Region', fontsize=12)
plt.ylabel('Total Consumption (kWh)', fontsize=12)

# 為了避免地區名字太長重疊在一起，我們把 X 軸的字轉 15 度
plt.xticks(rotation=15)

# tight_layout 會自動調整版面邊距，確保所有字體都不會被切到
plt.tight_layout()

# 顯示圖表！
plt.show()