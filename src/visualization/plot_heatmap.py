import pandas as pd
import folium
from branca.colormap import LinearColormap
from branca.element import Element
from pathlib import Path

# ==========================================
# 1. 動態路徑設定
# ==========================================
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
parquet_dir = project_root / "Denmark_weather" / "Weather_Regional_Split"
geojson_path = current_dir / "denmark_regions_simplified.geojson"
save_html_path = current_dir / "Denmark_Temperature_Only_2021_2025.html"

# ==========================================
# 2. 讀取並清洗五年氣溫資料
# ==========================================
print("🌡️ 正在從 Parquet 掃描 2021-2025 年氣溫資料...")
parquet_files = list(parquet_dir.glob("Weather_20*.parquet")) # 抓取所有年份

df_temp_list = []
for file_path in parquet_files:
    df = pd.read_parquet(file_path, columns=['observed_time', 'station_id', 'parameter_id', 'value', 'latitude', 'longitude'])
    df_temp_list.append(df[df['parameter_id'] == 'temp_dry'].copy())

print("🧮 正在執行資料清洗與月均溫聚合...")
df_temp_all = pd.concat(df_temp_list, ignore_index=True)

# 🛡️ 物理極限濾網：擋掉 -50度以下與異常高溫
df_temp_all = df_temp_all[(df_temp_all['value'] > -50) & (df_temp_all['value'] < 45)]

# 提取年份與月份並聚合
df_temp_all['year'] = df_temp_all['observed_time'].dt.year
df_temp_all['month'] = df_temp_all['observed_time'].dt.month
df_monthly_temp = df_temp_all.groupby(['station_id', 'latitude', 'longitude', 'year', 'month'])['value'].mean().reset_index()

print(f"✅ 成功計算出 {len(df_monthly_temp)} 筆月均溫資料點！")

# ==========================================
# 3. 準備地圖與色階
# ==========================================
m = folium.Map(location=[56.2, 11.5], zoom_start=7, tiles='cartodb dark_matter')

# 加入純粹的丹麥輪廓 (無電力填色)
if geojson_path.exists():
    folium.GeoJson(
        str(geojson_path),
        name="丹麥區域邊界",
        style_function=lambda x: {'fillColor': 'transparent', 'color': '#666666', 'weight': 1.5}
    ).add_to(m)

# 氣溫專屬色階
temp_colormap = LinearColormap(
    colors=['#313695', '#74add1', '#e0f3f8', '#fdae61', '#f46d43', '#a50026'],
    vmin=-2, vmax=20
)
temp_colormap.caption = '🌡️ 月平均氣溫 (°C)'
temp_colormap.add_to(m)

# ==========================================
# 4. 按「年_月」建立圖層
# ==========================================
print("🎨 正在繪製各年月氣溫圈圖層...")

layer_dict = {} # 紀錄給 JS 用的圖層變數名

# 巢狀迴圈：5年 x 12個月
for year in range(2021, 2026):
    for month in range(1, 13):
        # 建立專屬圖層
        layer_name = f"Y{year}_M{month}"
        fg = folium.FeatureGroup(name=layer_name, show=False)
        layer_dict[layer_name] = fg
        
        temp_data = df_monthly_temp[(df_monthly_temp['year'] == year) & (df_monthly_temp['month'] == month)]
        
        for _, row in temp_data.iterrows():
            lat, lon, temp = row['latitude'], row['longitude'], row['value']
            bg_color = temp_colormap(temp)
            
            html_icon = f"""
            <div style="
                background-color: {bg_color}; color: white; text-shadow: 1px 1px 2px black;
                border-radius: 50%; width: 32px; height: 32px;
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
                tooltip=f"<b>ID:</b> {row['station_id']}<br><b>{year}年{month}月均溫:</b> {temp:.1f}°C"
            ).add_to(fg)

        fg.add_to(m)

# ==========================================
# 5. 注入 JavaScript 年月雙重控制器
# ==========================================
print("⚙️ 正在注入年份與月份控制器...")

# 將 Python 建立的圖層變數名稱轉換為 JS 物件格式
js_layers = "{\n"
for name, fg in layer_dict.items():
    js_layers += f"      '{name}': {fg.get_name()},\n"
js_layers += "    }"

ui_html = """
<div style="position: fixed; bottom: 50px; left: 50px; width: 350px; z-index:9999; 
    background-color: rgba(255,255,255,0.95); border-radius: 8px; padding: 15px; 
    box-shadow: 0 4px 10px rgba(0,0,0,0.4); font-family: sans-serif;">
    <h4 style="margin: 0 0 10px 0; color: #111;">📅 丹麥氣溫時空分佈 (2021-2025)</h4>
    
    <div style="margin-bottom: 10px;">
        <label style="font-weight: bold; color: #333;">選擇年份: </label>
        <select id="year_select" style="padding: 5px; font-size: 14px; border-radius: 4px;">
            <option value="2021">2021 年</option>
            <option value="2022">2022 年</option>
            <option value="2023">2023 年</option>
            <option value="2024">2024 年</option>
            <option value="2025">2025 年</option>
        </select>
    </div>

    <label style="font-weight: bold; font-size: 16px; color: #d97706;">當前月份: <span id="month_label">1</span> 月</label>
    <input type="range" id="month_slider" min="1" max="12" value="1" style="width:100%; margin-top: 10px;">
</div>
"""

ui_js = f"""
<script>
document.addEventListener('DOMContentLoaded', function() {{
    var map = {m.get_name()};
    var layers = {js_layers};
    
    var yearSelect = document.getElementById('year_select');
    var monthSlider = document.getElementById('month_slider');
    var monthLabel = document.getElementById('month_label');

    function updateMap() {{
        var y = yearSelect.value;
        var m = monthSlider.value;
        var targetLayer = 'Y' + y + '_M' + m;
        
        monthLabel.innerText = m;

        // 隱藏全部圖層
        for (var key in layers) {{
            map.removeLayer(layers[key]);
        }}
        
        // 顯示被選中的圖層
        if (layers[targetLayer]) {{
            layers[targetLayer].addTo(map);
        }}
    }}

    // 綁定事件
    yearSelect.addEventListener('change', updateMap);
    monthSlider.addEventListener('input', updateMap);

    // 初始載入 2021 年 1 月
    updateMap();
}});
</script>
"""

m.get_root().html.add_child(Element(ui_html))
m.get_root().html.add_child(Element(ui_js))

m.save(save_html_path)
print(f"\n🎉 減法美學完成！純氣溫版動態地圖已儲存：{save_html_path}")