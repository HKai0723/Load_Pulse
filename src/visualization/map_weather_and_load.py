import pandas as pd
import numpy as np
import folium
import json
from pathlib import Path
from branca.colormap import LinearColormap
from branca.element import Element
import matplotlib.pyplot as plt
import scipy.interpolate as interp
import geojsoncontour

# ==========================================
# 1. 路徑設定
# ==========================================
current_dir = Path(__file__).resolve().parent
denmark_dir = current_dir.parent
project_root = denmark_dir.parent

save_html_path = current_dir / "Denmark_Weather_Monthly_PRO.html"
parquet_dir = project_root / "Denmark_weather" / "Weather_Regional_Split"

# 🌟 使用你提供的簡化版地圖檔名
geojson_path = current_dir / "denmark_regions_simplified.geojson"

# ==========================================
# 2. 讀取並計算「月平均氣溫」與「月平均風速」
# ==========================================
print("🌡️ 正在從 Parquet 讀取 2021 年氣象資料...")
parquet_files = list(parquet_dir.glob("Weather_2021_*.parquet"))

df_temp_list = []
df_wind_list = []

for file_path in parquet_files:
    df = pd.read_parquet(file_path, columns=['observed_time', 'station_id', 'parameter_id', 'value', 'latitude', 'longitude'])
    df_temp_list.append(df[df['parameter_id'] == 'temp_dry'].copy())
    df_wind_list.append(df[df['parameter_id'] == 'wind_speed'].copy())

print("🧮 正在聚合月均溫與風速網格...")
df_temp_all = pd.concat(df_temp_list, ignore_index=True)
df_temp_all['month'] = df_temp_all['observed_time'].dt.month
df_monthly_temp = df_temp_all.groupby(['station_id', 'latitude', 'longitude', 'month'])['value'].mean().reset_index()

df_wind_all = pd.concat(df_wind_list, ignore_index=True)
df_wind_all['month'] = df_wind_all['observed_time'].dt.month
df_monthly_wind = df_wind_all.groupby(['station_id', 'latitude', 'longitude', 'month'])['value'].mean().reset_index()

# ==========================================
# 3. 準備地圖、色階與底圖邊界
# ==========================================
print("🗺️ 正在生成地圖基底與丹麥輪廓...")
m = folium.Map(location=[56.2, 11.5], zoom_start=7, tiles='cartodb dark_matter')

# 加上丹麥的區域邊界 (增加科技感與辨識度)
if geojson_path.exists():
    folium.GeoJson(
        str(geojson_path),
        name="丹麥區域邊界",
        style_function=lambda x: {'fillColor': '#ffffff', 'fillOpacity': 0.03, 'color': '#555555', 'weight': 1.5}
    ).add_to(m)

temp_colormap = LinearColormap(
    colors=['#313695', '#74add1', '#e0f3f8', '#fdae61', '#f46d43', '#a50026'],
    vmin=-2, vmax=20
)
temp_colormap.caption = '🌡️ 月平均氣溫 (°C)'
temp_colormap.add_to(m)

# ==========================================
# 4. 按「月份」建立圖層
# ==========================================
print("🎨 正在繪製各月份的溫度圈與風速等高線...")

xi = np.linspace(8.0, 13.0, 60) # 稍微調低解析度，避免網頁吃太多記憶體
yi = np.linspace(54.5, 58.0, 60)
X, Y = np.meshgrid(xi, yi)

month_fgs = {} # 🌟 用來儲存 Python 的 FeatureGroup 物件

for month in range(1, 13):
    fg_month = folium.FeatureGroup(name=f"Month_{month}", show=False)
    month_fgs[month] = fg_month
    
    # --- 🌀 繪製風速等高線 ---
    wind_data = df_monthly_wind[df_monthly_wind['month'] == month].dropna()
    if len(wind_data) > 5:
        try:
            wind_points = wind_data[['longitude', 'latitude']].values
            wind_values = wind_data['value'].values
            Z = interp.griddata(wind_points, wind_values, (X, Y), method='linear')
            
            fig, ax = plt.subplots()
            contour = ax.contour(X, Y, Z, levels=5, cmap='PuBu', alpha=0.5)
            geojson_str = geojsoncontour.contour_to_geojson(contour=contour, ndigits=3)
            plt.close(fig)
            
            folium.GeoJson(
                json.loads(geojson_str),
                style_function=lambda x: {
                    'color': x['properties']['stroke'], 'weight': 2.5, 'opacity': 0.6, 'dashArray': '4, 6'
                }
            ).add_to(fg_month)
        except Exception as e:
            pass # 忽略無法內插的月份

    # --- 🌡️ 繪製帶數字的氣溫圈 ---
    temp_data = df_monthly_temp[df_monthly_temp['month'] == month]
    for _, row in temp_data.iterrows():
        lat, lon, temp = row['latitude'], row['longitude'], row['value']
        bg_color = temp_colormap(temp)
        
        html_icon = f"""
        <div style="
            background-color: {bg_color}; color: white; text-shadow: 1px 1px 2px black;
            border-radius: 50%; width: 34px; height: 34px;
            display: flex; justify-content: center; align-items: center;
            font-size: 11px; font-weight: bold; border: 2px solid white;
            opacity: 0.9; box-shadow: 2px 2px 4px rgba(0,0,0,0.6);
        ">
            {temp:.1f}°
        </div>
        """
        
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(html=html_icon),
            tooltip=f"<b>ID:</b> {row['station_id']}<br><b>{month}月均溫:</b> {temp:.1f}°C"
        ).add_to(fg_month)

    fg_month.add_to(m)

# ==========================================
# 5. 注入防呆版 JavaScript 動態時間軸
# ==========================================
print("⚙️ 正在注入動態互動腳本...")

# 🌟 暴力解法：直接讓 Python 告訴 JS 每個圖層對應的內部變數名稱！
js_layer_dict = "{\n" + ",\n".join([f"      {m}: {fg.get_name()}" for m, fg in month_fgs.items()]) + "\n    }"

slider_html = """
<div style="position: fixed; bottom: 50px; left: 50px; width: 350px; z-index:9999; 
    background-color: rgba(255,255,255,0.95); border-radius: 8px; padding: 15px; 
    box-shadow: 0 4px 10px rgba(0,0,0,0.4); font-family: sans-serif;">
    <h4 style="margin: 0 0 10px 0; color: #111;">📅 2021年 氣候動態推演</h4>
    <label style="font-weight: bold; font-size: 16px; color: #d97706;">當前月份: <span id="month_label">1</span> 月</label>
    <input type="range" id="month_slider" min="1" max="12" value="1" style="width:100%; margin-top: 10px;">
    <div style="font-size: 12px; color: #555; margin-top: 5px;">
        💡 虛線為風速等高線，圓圈為測站均溫
    </div>
</div>
"""

slider_js = f"""
<script>
document.addEventListener('DOMContentLoaded', function() {{
    var map = {m.get_name()};
    
    // 🌟 直接接收 Python 傳遞過來的底層物件，100% 不會抓錯
    var monthLayers = {js_layer_dict};

    // 初始化：先清空全部，只留 1 月
    for (var key in monthLayers) {{
        map.removeLayer(monthLayers[key]);
    }}
    monthLayers[1].addTo(map);

    var slider = document.getElementById('month_slider');
    var label = document.getElementById('month_label');

    slider.addEventListener('input', function(e) {{
        var m = parseInt(e.target.value);
        label.innerText = m;
        
        for (var key in monthLayers) {{
            map.removeLayer(monthLayers[key]);
        }}
        if (monthLayers[m]) {{
            monthLayers[m].addTo(map);
        }}
    }});
}});
</script>
"""

m.get_root().html.add_child(Element(slider_html))
m.get_root().html.add_child(Element(slider_js))

m.save(save_html_path)
print(f"\n🎉 完美破關！底圖已加上，請重新開啟確認：{save_html_path}")