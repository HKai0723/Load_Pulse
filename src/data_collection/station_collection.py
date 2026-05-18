import requests
import pandas as pd
from pathlib import Path

# ==========================================
# 1. 設定儲存路徑
# ==========================================
current_dir = Path(__file__).resolve().parent
output_csv = current_dir / "dmi_active_stations_list.csv"

# ==========================================
# 2. 發送 DMI API 請求 (免 API Key)
# ==========================================
url = "https://dmigw.govcloud.dk/v2/metObs/collections/station/items"
params = {
    "limit": 10000,
    "status": "Active"  # 🎯 只拉取目前「活躍中」的測站，減輕後續篩選負擔
}

print("🌐 正在連線至丹麥 DMI 官方 API 請求測站清單...")
try:
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status() # 檢查連線狀態
    geojson_data = response.json()
    print(f"✨ 成功下載！從 API 取得共 {len(geojson_data['features'])} 個活躍測站。")
    
except Exception as e:
    print(f"❌ API 請求失敗，錯誤訊息: {e}")
    exit()

# ==========================================
# 3. 解析 GeoJSON 結構並打平成表格
# ==========================================
stations_list = []

for feature in geojson_data['features']:
    props = feature['properties']
    geom = feature['geometry']
    
    # 擷取核心欄位
    station_info = {
        "station_id": str(props.get("stationId")).zfill(5), # 🛡️ 防呆：直接自動補零
        "name": props.get("name"),
        "country": props.get("country"),
        "status": props.get("status"),
        "station_type": props.get("type"), # 測站類型 (如: Synop, Pluvio)
        "latitude": geom['coordinates'][1] if geom else None,  # 緯度
        "longitude": geom['coordinates'][0] if geom else None, # 經度
        "created_at": props.get("created"),
        "updated_at": props.get("updated")
    }
    stations_list.append(station_info)

# ==========================================
# 4. 轉換為 DataFrame 並儲存 CSV
# ==========================================
df_stations = pd.DataFrame(stations_list)

# 按照測站 ID 排序，方便對照
df_stations = df_stations.sort_values(by="station_id").reset_index(drop=True)

# 匯出 CSV
df_stations.to_csv(output_csv, index=False, encoding="utf-8-sig")

print("\n📊 DMI 官方測站清單（前 5 筆樣貌）：")
print(df_stations.head().to_string(index=False))

print(f"\n💾 測站清單已成功匯出至：\n👉 {output_csv}")
print("💡 同學拿到這張表後，就能用裡面的 station_id、status 和 country 去做精準的資料過濾了！")