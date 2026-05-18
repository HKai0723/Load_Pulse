import sqlite3
import pandas as pd
from pathlib import Path

# ==========================================
# 1. 路徑設定
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "denmark_weather_ALL.db"
# 讀取我們昨天畫地圖前產生的分類總表
CLASSIFIED_CSV = BASE_DIR / "stations_classified.csv" 
# 我們即將產出的最新對照表
OUTPUT_CSV = BASE_DIR / "active_stations_2021H1_mapping.csv"

def generate_mapping():
    print("🔌 連接資料庫，撈取 1~6 月活躍測站 ID...")
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT DISTINCT station_id 
        FROM weather_all 
        WHERE observed_time >= '2021-01-01' 
          AND observed_time < '2021-07-01'
    """
    df_db_stations = pd.read_sql_query(query, conn)
    conn.close()
    
    # 將 DB 裡的 ID 轉成 List
    active_ids = df_db_stations['station_id'].dropna().unique().tolist()
    
    if not CLASSIFIED_CSV.exists():
        print(f"❌ 找不到分類總表 {CLASSIFIED_CSV.name}，請確認檔案位置。")
        return

    print("📊 正在與分類總表進行交叉比對...")
    df_classified = pd.read_csv(CLASSIFIED_CSV)
    
    # 清理 Excel 防呆字元 (把 '="06190"' 洗成 '06190')
    df_classified['乾淨的測站ID'] = df_classified['測站ID'].astype(str).str.replace('="', '').str.replace('"', '')

# 【核心對照邏輯】只留下在 active_ids 裡面的測站
    df_active = df_classified[df_classified['乾淨的測站ID'].isin(active_ids)].copy()
    
    # 🌟 剔除重複的測站 ID，保留最後一筆（通常是最新狀態）
    df_active = df_active.drop_duplicates(subset=['乾淨的測站ID'], keep='last')
    
    # 存檔前整理一下欄位順序，把乾淨的 ID 移到最前面
    cols = ['乾淨的測站ID', '站名', '所屬區域', '生命週期', '狀態', '緯度', '經度']
    df_active = df_active[cols]
    
    df_active.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"✅ 對照表產出成功！已儲存為：{OUTPUT_CSV.name}")
    print("\n" + "="*40)
    print("🏆 2021 上半年活躍測站 (245站) 的區域分佈統計：")
    print("="*40)
    
    # 印出各區的測站數量統計
    region_counts = df_active['所屬區域'].value_counts()
    print(region_counts.to_string())

if __name__ == "__main__":
    generate_mapping()