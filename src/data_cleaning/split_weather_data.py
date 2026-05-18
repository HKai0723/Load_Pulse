import sqlite3
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import time
import json
from pathlib import Path
from shapely.geometry import shape, Point

# ==========================================
# 1. 路徑設定
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
project_root = BASE_DIR.parent
DB_PATH = BASE_DIR / "denmark_weather_ALL.db"
CLASSIFIED_CSV = BASE_DIR / "stations_classified.csv"
GEOJSON_PATH = project_root / "Denmark" / "Geo" / "denmark_regions_highres.geojson"

OUT_DIR = BASE_DIR / "Weather_Regional_Split"
OUT_DIR.mkdir(exist_ok=True)

print("🚀 啟動大數據引擎：循序掃描模式 (Sequential Scan)")
print(f"📁 專屬資料夾已就緒：{OUT_DIR}")

# ==========================================
# 2. 預先建立【測站 -> 區域】的高速映射字典
# ==========================================
print("🗺️ 正在建立空間與測站的對照表...")
with open(GEOJSON_PATH, 'r', encoding='utf-8') as f:
    geo_data = json.load(f)

region_polygons = {f['properties']['navn']: shape(f['geometry']) for f in geo_data['features']}

df_stations = pd.read_csv(CLASSIFIED_CSV)
df_stations['乾淨ID'] = df_stations['測站ID'].astype(str).str.replace('="', '').str.replace('"', '')

def get_region(lon, lat):
    if pd.isna(lon) or pd.isna(lat): return None
    pt = Point(lon, lat)
    for r_name, r_poly in region_polygons.items():
        if r_poly.contains(pt): return r_name
    return "離島或海外領地及海域"

df_stations['所屬區域'] = df_stations.apply(lambda row: get_region(row['經度'], row['緯度']), axis=1)

# 🌟 核心魔法：建立 Python 字典，查找速度 O(1)
station_to_region = dict(zip(df_stations['乾淨ID'], df_stations['所屬區域']))

# ==========================================
# 3. 循序讀取與分發 (Chunking + Routing)
# ==========================================
print(f"🔗 正在連線 78.1 GB 資料庫，準備進行全表串流掃描...")
conn = sqlite3.connect(DB_PATH)

# 一次吃 300 萬筆 (約佔用 1.5GB 記憶體，非常安全)
CHUNK_SIZE = 3_000_000 
query = "SELECT observed_time, station_id, parameter_id, value, latitude, longitude FROM weather_all"

writers = {}
start_time = time.time()
chunk_count = 0
total_processed = 0

try:
    for df_chunk in pd.read_sql_query(query, conn, chunksize=CHUNK_SIZE):
        chunk_start = time.time()
        
        # 1. 轉換時間並萃取年份
        df_chunk['observed_time'] = pd.to_datetime(df_chunk['observed_time'])
        df_chunk['year'] = df_chunk['observed_time'].dt.year
        
        # 2. 透過字典瞬間完成區域分配
        df_chunk['region'] = df_chunk['station_id'].map(station_to_region)
        
        # 3. 丟棄不在我們研究範圍(無區域)的無效資料
        df_chunk = df_chunk.dropna(subset=['region', 'year'])
        
        # 4. 分群寫入 30 個 Parquet 檔案
        for (y, r), group_df in df_chunk.groupby(['year', 'region']):
            y = int(y)
            # 移除暫時的路由欄位
            out_df = group_df.drop(columns=['year', 'region'])
            table = pa.Table.from_pandas(out_df, preserve_index=False)
            
            writer_key = (y, r)
            
            # 如果是第一次遇到這個 (年份, 區域) 組合，就動態開啟一個新檔案
            if writer_key not in writers:
                safe_region = str(r).replace(" ", "_").replace("/", "_")
                out_filename = OUT_DIR / f"Weather_{y}_{safe_region}.parquet"
                writers[writer_key] = pq.ParquetWriter(out_filename, table.schema)
                
            # 將資料附加寫入該檔案
            writers[writer_key].write_table(table)
            
        total_processed += len(df_chunk)
        chunk_count += 1
        elapsed = time.time() - chunk_start
        print(f"📦 已處理區塊 {chunk_count:03d} | 累積路由 {total_processed:,} 筆 | 區塊耗時 {elapsed:.1f} 秒")

finally:
    # 確保所有檔案安全關閉
    for writer in writers.values():
        writer.close()
    conn.close()

total_elapsed = (time.time() - start_time) / 60
print(f"\n🎉🎉🎉 完美切分完畢！")
print(f"總共處理了 {total_processed:,} 筆資料，耗時 {total_elapsed:.2f} 分鐘！")
print(f"請前往 {OUT_DIR} 驗收你的 30 份黃金戰備檔案！")