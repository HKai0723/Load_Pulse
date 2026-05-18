import geopandas as gpd
from pathlib import Path

# 1. 動態定位路徑
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent 

# 🗺️ 載入五大區地圖檔
regions_geojson = current_dir / "denmark_regions_highres.geojson"
# 🎯 載入你手上的測站 GeoJSON 檔！
stations_geojson = project_root / "Denmark_weather" / "denmark_stations.geojson"

print("🌍 正在載入地理資料並進行空間比對...")

# 2. 載入行政區地圖
regions = gpd.read_file(regions_geojson)

# 3. 直接載入測站 GeoJSON！(超方便，它會自動處理好所有經緯度點位)
gdf_stations = gpd.read_file(stations_geojson)

# 確保兩者座標系統一致
if gdf_stations.crs != regions.crs:
    gdf_stations = gdf_stations.to_crs(regions.crs)

# 4. 執行空間連接 (Spatial Join)
joined = gpd.sjoin(gdf_stations, regions, how="left", predicate="within")

# 5. 統計結果 ('navn' 是五大區地圖裡的名稱欄位)
station_counts = joined['navn'].value_counts(dropna=False).reset_index()
station_counts.columns = ['行政區域', '測站數量']

# 處理沒有對應到五大區的測站
station_counts['行政區域'] = station_counts['行政區域'].fillna('非本島 (格陵蘭/法羅群島等)')

# 6. 輸出報告
print("\n=== 丹麥氣象測站分佈統計報告 ===")
print(station_counts.to_string(index=False))