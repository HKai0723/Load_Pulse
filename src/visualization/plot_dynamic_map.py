import pandas as pd
import plotly.express as px
import json

# 1. 設定路徑
csv_path = r"C:\school\Load_Pulse\Denmark\Clean_Consumption_Wide.csv"
geojson_path = r"C:\school\Load_Pulse\Denmark\Geo\denmark_regions_simplified.geojson"
save_html_path = r"C:\school\Load_Pulse\Denmark\Geo\Denmark_Dynamic_Load.html"

# 2. 讀取並處理資料 (資料壓縮邏輯)
print("📦 正在讀取資料並轉換為『按月加總』模式...")
df = pd.read_csv(csv_path)

# 將字串格式的時間轉成真正的 Python 時間物件
df['TimeUTC'] = pd.to_datetime(df['TimeUTC'])

# 新增『年-月』欄位，方便我們按月分組
df['YearMonth'] = df['TimeUTC'].dt.strftime('%Y-%m')

# 計算每個月的總用電量 (Y 軸)
df['Total_Load'] = df['load_private'] + df['load_business'] + df['load_public']

# 💡 資工小技巧：按月份與地區分組，把 4 萬筆資料濃縮成 60 個月 (5年 x 12月)
monthly_df = df.groupby(['YearMonth', 'RegionName'])['Total_Load'].sum().reset_index()

# 3. 讀取地圖骨架 (處理編碼幽靈)
print("🔑 讀取地圖骨架並進行最終對齊...")
with open(geojson_path, 'r', encoding='utf-8') as f:
    geojson_data = json.load(f)

# 同樣使用之前的「偷鑰匙」邏輯，確保 Sjælland 不會變黑洞
geo_regions = [feature['properties']['navn'] for feature in geojson_data['features']]
sj_name = [n for name in geo_regions if 'Sj' in (n := str(name))][0]
monthly_df.loc[monthly_df['RegionName'].str.contains('Sj', na=False), 'RegionName'] = sj_name

# 4. 繪製動態地圖 (改用強大的 Mapbox 引擎)
print("🎨 正在產生動態熱力圖 (使用 Mapbox 引擎)...")
fig = px.choropleth_mapbox(
    monthly_df,
    geojson=geojson_data,
    locations='RegionName',
    featureidkey='properties.navn',
    color='Total_Load',
    animation_frame='YearMonth',
    color_continuous_scale='YlOrRd',
    range_color=[monthly_df['Total_Load'].min(), monthly_df['Total_Load'].max()],
    mapbox_style="carto-positron",      # 🌟 加上這行，就會有跟 Folium 一樣漂亮的底圖
    zoom=5.5,                           # 設定預設縮放大小
    center={"lat": 56.2, "lon": 10.5},  # 設定丹麥的中心座標
    opacity=0.7,
    title='Denmark Monthly Electricity Pulse (2021-2025)',
    labels={'Total_Load': 'kWh'}
)

# 把邊界留白縮到最小，讓地圖更滿版 (注意：原本的 update_geos 可以刪掉了)
fig.update_layout(margin={"r":0,"t":50,"l":0,"b":0})

# 5. 存檔並自動打開
fig.write_html(save_html_path)
print(f"🎉 任務達成！動態地圖已儲存：{save_html_path}")

# 如果你是在本地端執行，可以加上這行直接彈出瀏覽器
import webbrowser
webbrowser.open('file://' + save_html_path)