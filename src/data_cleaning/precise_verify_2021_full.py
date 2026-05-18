import sqlite3
import pandas as pd
from pathlib import Path

# ==========================================
# 1. 路徑設定
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
# 來源 1：包含精確 validFrom 與 validTo 的官方名冊
INFO_CSV = BASE_DIR / "denmark_stations_info.csv"
# 來源 2：你辛苦抓下的千萬筆真實氣象資料庫
DB_PATH = BASE_DIR / "denmark_weather_ALL.db"

def exact_comparison_full_year():
    print("🔍 啟動 2021 【全年】精準對決模式...")
    
    # ==========================================
    # 階段 A：計算「理論上」該有資料的測站 (Metadata)
    # ==========================================
    df_info = pd.read_csv(INFO_CSV)
    
    # 清理 ID 格式
    df_info['乾淨ID'] = df_info['測站ID'].astype(str).str.replace('="', '').str.replace('"', '')

    # 強制轉換時間並拔除時區
    df_info['start_dt'] = pd.to_datetime(df_info['validFrom'], errors='coerce').dt.tz_localize(None)
    df_info['end_dt'] = pd.to_datetime(df_info['validTo'], errors='coerce').dt.tz_localize(None)

# 🌟 修改：對齊資料庫實際的終點
    target_start = pd.Timestamp('2021-01-01 00:00:00')
    target_end = pd.Timestamp('2021-12-23 23:59:59')

    # 【精準邏輯】：在這個時間窗內活著的測站
    mask = (
        (df_info['start_dt'].isna() | (df_info['start_dt'] <= target_end)) & 
        (df_info['end_dt'].isna() | (df_info['end_dt'] >= target_start))
    )

    theoretical_df = df_info[mask]
    theoretical_ids = set(theoretical_df['乾淨ID'].tolist())
    
    # ==========================================
    # 階段 B：計算「實際上」真有資料的測站 (Database)
    # ==========================================
    conn = sqlite3.connect(DB_PATH)
    # 🌟 修改 2：資料庫撈取範圍改為整個 2021 年
    query = """
        SELECT DISTINCT station_id 
        FROM weather_all 
        WHERE observed_time >= '2021-01-01' 
          AND observed_time < '2021-12-23 23:59:59'
    """
    df_db = pd.read_sql_query(query, conn)
    conn.close()

    actual_ids = set(df_db['station_id'].tolist())

    # ==========================================
    # 階段 C：殘酷舞台交叉比對
    # ==========================================
    intersection = theoretical_ids & actual_ids
    ghosts = theoretical_ids - actual_ids
    orphans = actual_ids - theoretical_ids

    print("\n" + "="*50)
    print("🏆 丹麥氣象站 2021 【全年】 真實度體檢報告")
    print("="*50)
    print(f"📋 官方名冊宣稱 2021 應該活著的測站： {len(theoretical_ids)} 站")
    print(f"📊 資料庫實際撈到 2021 有資料的測站： {len(actual_ids)} 站")
    print("-" * 50)
    print(f"✅ 完美吻合 (名冊有，且真有資料)： {len(intersection)} 站")
    print(f"👻 幽靈測站 (名冊有，但完全沒資料)： {len(ghosts)} 站")
    
    if orphans:
        print(f"👽 偷跑測站 (名冊沒有或已死，卻有資料)： {len(orphans)} 站")
    
    if len(ghosts) > 0:
        print("\n💡 幽靈測站可能原因：")
        print("1. 感測器損壞但官方未註銷 (佔多數)。")
        print("2. 屬於潮汐、地下水位等特殊感測器，未提供一般氣象數據。")
        print("3. 剛好在 2021 整年都在大修或斷電。")

if __name__ == "__main__":
    exact_comparison_full_year()