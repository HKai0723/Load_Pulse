import os
import pandas as pd
import folium
import geopandas as gpd
from shapely.geometry import Point

def main():
    # 1. 動態定位專案根目錄
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.abspath(os.path.join(current_dir, "..", ".."))

    csv_path = os.path.join(base_dir, "data", "raw", "dim_stations.csv")
    # 🌟 這裡自動改成你換過的高精度地圖路徑
    geojson_path = os.path.join(base_dir, "data", "spatial", "denmark_regions_simplified.geojson")
    output_html_path = os.path.join(base_dir, "outputs", "figures", "Denmark_60_Stations_Regional.html")

    # 2. 讀取資料並篩選 6019-6097
    print(f"正在讀取完整測站資料: {csv_path}")
    df = pd.read_csv(csv_path)
    df['station_num'] = pd.to_numeric(df['stationId'], errors='coerce')
    df_filtered = df[df['station_num'].between(6019, 6097)].copy()
    print(f"成功篩選出符合 6019-6097 範圍的目標測站，總計: {len(df_filtered)} 個")

    # 3. 讀取區域地圖
    #print(f"正在載入丹麥區域高精度地圖: {geojson_path}")
    gdf_regions = gpd.read_file(geojson_path)
    
    # 把地圖資料中的時間物件（Timestamp）全部轉成純文字
    for col in gdf_regions.columns:
        if gdf_regions[col].dtype == 'object' or str(gdf_regions[col].dtype).startswith('datetime'):
            if gdf_regions[col].apply(lambda x: isinstance(x, pd.Timestamp)).any():
                gdf_regions[col] = gdf_regions[col].astype(str)

    region_column = 'navn'
    #print(f"🎯 成功對齊！使用地圖的區域名稱欄位: '{region_column}'")

# 4. 空間分析：將測站點配對到行政區 (Spatial Join)
    print("正在進行空間分區分析...")
    geometry = [Point(xy) for xy in zip(df_filtered['lon'], df_filtered['lat'])]
    gdf_stations = gpd.GeoDataFrame(df_filtered, geometry=geometry, crs="EPSG:4326")
    
    # 嚴格比對 within
    joined = gpd.sjoin(gdf_stations, gdf_regions[['geometry', region_column]], how='left', predicate='within')
    
    # 海岸線自動吸附防呆
    sea_mask = joined[region_column].isna()
    if sea_mask.any():
        print(f"💡 偵測到有 {sea_mask.sum()} 個測站落在陸地邊界外，啟動海岸線自動吸附機制...")
        sea_stations = joined[sea_mask].drop(columns=[region_column, 'index_right'])
        snapped_stations = gpd.sjoin_nearest(sea_stations, gdf_regions[['geometry', region_column]], how='left')
        joined.loc[sea_mask, region_column] = snapped_stations[region_column].values

    # 🌟 既然全部都完美吸附回陸地，直接使用該欄位，不再填補 "Other/Sea"
    joined['region'] = joined[region_column]

    # 5. 統計各區數量 (這時候只會剩下真正的五大區數據)
    stats = joined['region'].value_counts().to_dict()
    total_count = len(joined)

    # 6. 設定五大區顏色對應 (乾淨清爽，不留灰色海域選項)
    color_map = {
        "Region Hovedstaden": "purple",
        "Region Midtjylland": "blue",
        "Region Nordjylland": "darkblue",
        "Region Sjælland": "green",
        "Region Syddanmark": "orange"
    }

    # 7. 建立 Folium 地圖
    m = folium.Map(location=[56.0, 11.0], zoom_start=7, tiles="CartoDB positron")

    # 畫上背景區域輪廓
    folium.GeoJson(
        gdf_regions,
        style_function=lambda x: {
            "fillColor": color_map.get(x['properties'].get(region_column), "#AAAAAA"),
            "color": "#666666",
            "weight": 1.5,
            "fillOpacity": 0.15
        }
    ).add_to(m)

    # 8. 投影 24 個測站
    for idx, row in joined.iterrows():
        r = row['region']
        marker_color = color_map.get(r, "gray")
        station_id_str = str(row['stationId']).zfill(5)
        
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.8,
            popup=f"ID: {station_id_str}<br>Region: {r}",
            tooltip=f"ID: {station_id_str}"
        ).add_to(m)

    # 9. 建立角落統計表 (因為 stats 是從 value_counts 來的，沒出現的 region 根本不會進迴圈，表格絕對純淨)
    stats_html = f'''
        <div style="position: fixed; 
                    bottom: 20px; right: 20px; width: 240px; height: auto; 
                    background-color: white; border: 2px solid #666; 
                    z-index: 9999; font-size: 13px; padding: 12px;
                    border-radius: 6px; box-shadow: 2px 2px 6px rgba(0,0,0,0.2);
                    font-family: sans-serif;">
            <b style="font-size: 14px;">6019-6097 測站區域統計</b><br>
            <hr style="margin: 6px 0; border: 0; border-top: 1px solid #ccc;">
            <table style="width: 100%; border-collapse: collapse;">
    '''
    for region, count in stats.items():
        c = color_map.get(region, "gray")
        stats_html += f'<tr><td style="padding: 2px 0;"><span style="color:{c}; font-size:16px;">●</span> {region}</td><td align="right" style="font-weight:bold;">{count}</td></tr>'
    
    stats_html += f'''
            <tr style="font-weight: bold; border-top: 1px solid #666;">
                <td style="padding-top: 6px;">Total Stations</td><td align="right" style="padding-top: 6px;">{total_count}</td>
            </tr>
            </table>
        </div>
    '''
    m.get_root().html.add_child(folium.Element(stats_html))

    # 10. 儲存 HTML
    m.save(output_html_path)
    print(f"🎉 帶分區統計的地圖已完美生成！請查看: {output_html_path}")

if __name__ == "__main__":
    main()