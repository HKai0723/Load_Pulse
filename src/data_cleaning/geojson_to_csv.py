import json
import os
import pandas as pd

# 自動抓取程式所在的資料夾路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_GEOJSON = os.path.join(BASE_DIR, 'denmark_stations.geojson')
OUTPUT_CSV = os.path.join(BASE_DIR, 'denmark_stations_info.csv')

def extract_station_info():
    # 檢查檔案是否存在
    if not os.path.exists(INPUT_GEOJSON):
        print(f"❌ 找不到檔案: {INPUT_GEOJSON}")
        return

    print("讀取 GeoJSON 檔案中...")
    with open(INPUT_GEOJSON, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stations = []
    features = data.get('features', [])
    
    for feature in features:
        # 所有測站的詳細屬性都藏在 properties 裡面
        props = feature.get('properties', {})
        
        station_id = props.get('stationId', '')
        name = props.get('name', '未知站名')
        status = props.get('status', '未知狀態')
        
        # 🌟 關鍵修正：同時提取啟用與關停時間，並保持原始格式(無資料就留空)
        valid_from = props.get('validFrom', None)
        valid_to = props.get('validTo', None)
        
        # 提取座標 (經度, 緯度)
        coords = feature.get('geometry', {}).get('coordinates', [None, None])
        lon = coords[0] if len(coords) >= 1 else None
        lat = coords[1] if len(coords) >= 2 else None

        stations.append({
            '測站ID': f'="{station_id}"',  # 加上 ="..." 的魔法，防止 Excel 吞掉開頭的 0
            '站名': name,
            '狀態': status,
            'validFrom': valid_from,      # 🌟 配合後續判斷，直接使用標準欄位名稱
            'validTo': valid_to,          # 🌟 新增關停時間欄位
            '經度': lon,
            '緯度': lat
        })

    # 轉成 DataFrame 並輸出
    df = pd.DataFrame(stations)
    df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 成功提取 {len(df)} 個測站資訊！(包含啟用與關停時間)")
    print(f"💾 檔案已完美儲存為: {OUTPUT_CSV}")

if __name__ == "__main__":
    extract_station_info()