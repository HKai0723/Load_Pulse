import pandas as pd
import folium
import json
from pathlib import Path
from branca.element import Element
from shapely.geometry import shape, Point

# ==========================================
# 1. 動態路徑設定
# ==========================================
current_dir = Path(__file__).resolve().parent
denmark_dir = current_dir.parent
project_root = denmark_dir.parent

csv_path = denmark_dir / "Clean_Consumption_Wide.csv"
geojson_path = current_dir / "denmark_regions_highres.geojson"
save_html_path = current_dir / "Denmark_Load_and_Stations.html"

# 🌟 我們修復好的分類檔
classified_csv_path = project_root / "Denmark_weather" / "stations_classified.csv"

# ==========================================
# 2. 處理邊界與用電量資料
# ==========================================
print("🗺️ 正在載入邊界與用電量資料...")
with open(geojson_path, 'r', encoding='utf-8') as f:
    geo_data = json.load(f)

# 準備好空間計算用的多邊形字典 (用來即時算測站屬於哪一區)
region_polygons = {f['properties']['navn']: shape(f['geometry']) for f in geo_data['features']}

df_load = pd.read_csv(csv_path)
df_load['Total_Load'] = df_load['load_private'] + df_load['load_business'] + df_load['load_public']
region_sum = df_load.groupby('RegionName')['Total_Load'].sum().reset_index()

geo_regions = list(region_polygons.keys())
sj_names = [name for name in geo_regions if 'Sj' in name]
if sj_names:
    region_sum.loc[region_sum['RegionName'].str.contains('Sj', na=False), 'RegionName'] = sj_names[0]

m = folium.Map(location=[56.2, 11.5], zoom_start=7, tiles='cartodb positron')

folium.Choropleth(
    geo_data=geo_data,               
    name='⚡ 區域用電量熱力圖',
    data=region_sum,
    columns=['RegionName', 'Total_Load'], 
    key_on='feature.properties.navn', 
    fill_color='YlOrRd', 
    fill_opacity=0.6, line_opacity=0.3,
    legend_name='Total Electricity Consumption (kWh) 2021-2025'
).add_to(m)

# ==========================================
# 3. 讀取 CSV 並進行地圖標點與空間計算
# ==========================================
print("📍 正在讀取 stations_classified.csv 進行地圖標點...")
if not classified_csv_path.exists():
    print(f"❌ 找不到分類檔：{classified_csv_path}")
    exit()

df_stations = pd.read_csv(classified_csv_path)

# 建立圖層
fg_old = folium.FeatureGroup(name="🟢 2021前活到現在")
fg_new = folium.FeatureGroup(name="🔵 2021~2025新增")
fg_dead = folium.FeatureGroup(name="⚫ 2021~2025死亡")
fg_ignore = folium.FeatureGroup(name="⚪ 2021前已死亡/其他", show=False)

# 走訪 CSV 裡的每一列資料來畫點
for index, row in df_stations.iterrows():
    # 防呆處理，避免有些經緯度是空的
    if pd.isna(row['緯度']) or pd.isna(row['經度']):
        continue
    
    lon, lat = row['經度'], row['緯度']
    pt = Point(lon, lat)
    
    # 🌟 即時空間計算：判斷這個點落在哪個多邊形內
    located_region = "離島或海外領地及海域"
    for r_name, r_poly in region_polygons.items():
        if r_poly.contains(pt):
            located_region = r_name
            break
            
    lifecycle = str(row['生命週期'])
    marker_color = '#000000' # 預設黑色
    target_layer = fg_ignore
    
    # 根據文字決定顏色
    if '2021前活到現在' in lifecycle:
        marker_color = '#16a34a'
        target_layer = fg_old
    elif '2021~2025新增' in lifecycle:
        marker_color = '#2563eb'
        target_layer = fg_new
    elif '2021~2025死亡' in lifecycle:
        marker_color = '#4b5563'
        target_layer = fg_dead
    elif '2025後新增' in lifecycle:
        marker_color = '#9333ea'
        target_layer = fg_ignore

    html_tooltip = f"""
    <div style="font-family: Arial, sans-serif; min-width: 200px;">
        <h4 style="margin: 0 0 5px 0; color: #333;">{row['站名']}</h4>
        <b>ID:</b> {str(row['測站ID']).replace('="','').replace('"','')}<br>
        <b>區域:</b> {located_region}<br>
        <b>狀態:</b> {row['狀態']}<br>
        <b>分類:</b> <span style="color: {marker_color}; font-weight: bold;">{lifecycle}</span>
    </div>
    """
    
    folium.CircleMarker(
        location=[lat, lon],
        radius=5, weight=1.5, color='white',
        fill_color=marker_color, fill_opacity=0.9,
        tooltip=folium.Tooltip(html_tooltip)
    ).add_to(target_layer)

for fg in [fg_old, fg_new, fg_dead, fg_ignore]:
    fg.add_to(m)

# ==========================================
# 4. 注入即時統計面板 (JS & HTML)
# ==========================================
stats_html = """
<div style="position: fixed; bottom: 50px; left: 50px; width: 220px; z-index:9999; 
    background-color: white; border: 2px solid grey; border-radius: 6px; padding: 10px; 
    font-size: 14px; font-family: 'Noto Sans TC', sans-serif; box-shadow: 2px 2px 5px rgba(0,0,0,0.3);">
    <h4 style="margin: 0 0 10px 0; border-bottom: 1px solid #ccc;">📍 畫面上測站數量</h4>
    <div id="stats-content">正在計算中...</div>
</div>
"""
stats_js = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    var map = %s;
    function updateStats() {
        var c = { old:0, new:0, dead:0 };
        map.eachLayer(function(layer) {
            if (layer instanceof L.CircleMarker) {
                var col = layer.options.fillColor;
                if (col === '#16a34a') c.old++;
                if (col === '#2563eb') c.new++;
                if (col === '#4b5563') c.dead++;
            }
        });
        document.getElementById('stats-content').innerHTML = 
            '🟢 2021前活到現在: ' + c.old + '<br>' +
            '🔵 2021~2025新增: ' + c.new + '<br>' +
            '⚫ 2021~2025死亡: ' + c.dead + '<br><hr>' +
            '<b>當前顯示總計: ' + (c.old + c.new + c.dead) + '</b>';
    }
    map.on('overlayadd', updateStats);
    map.on('overlayremove', updateStats);
    setTimeout(updateStats, 1000);
});
</script>
""" % m.get_name()

m.get_root().html.add_child(Element(stats_html))
m.get_root().html.add_child(Element(stats_js))

folium.LayerControl(collapsed=False).add_to(m)
m.save(save_html_path)
print(f"\n🎉 大功告成！直接讀取 CSV 並精準計算區域的地圖已儲存：{save_html_path}")