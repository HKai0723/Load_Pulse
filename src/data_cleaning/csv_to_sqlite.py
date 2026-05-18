import pandas as pd
import sqlite3
import os

# 1. 設定你的工作路徑與檔案名稱
folder_path = r"C:\school\Load_Pulse\Denmark"

# 你指定的清洗後 CSV 檔名
csv_file_name = "Clean_Consumption_Wide.csv" 
csv_file_path = os.path.join(folder_path, csv_file_name)

# 設定要輸出的 SQLite 資料庫檔名 (與 CSV 檔名相對應)
db_file_name = "Clean_Consumption_Wide.db"
db_file_path = os.path.join(folder_path, db_file_name)

print(f"📥 正在讀取清洗好的 CSV 檔案: {csv_file_name} ...")

try:
    # 2. 讀取 CSV 檔案
    # 加上 low_memory=False 避免大檔案讀取時的記憶體警告
    df = pd.read_csv(csv_file_path, low_memory=False)
    print(f"✅ 成功讀取 {len(df)} 筆資料！")
    
    # 3. 連線並寫入 SQLite 資料庫
    print(f"🔌 正在建立並寫入 SQLite 資料庫: {db_file_name} ...")
    conn = sqlite3.connect(db_file_path)
    
    # 將 DataFrame 寫入資料庫
    # name='power_data' 是資料庫裡面的「資料表(Table)名稱」
    # if_exists='replace' 代表如果這個資料表已經存在，就直接覆蓋掉，確保資料是最新的
    df.to_sql(name='power_data', con=conn, if_exists='replace', index=False)
    
    # 關閉連線
    conn.close()
    
    print(f"🎉 任務完成！你現在同時擁有 CSV 和 .db 兩種格式的寬表格資料了！")
    print(f"📂 準備上繳的資料庫檔案位置：{db_file_path}")

except FileNotFoundError:
    print(f"❌ 找不到檔案！請確認 {csv_file_name} 是否真的放在 {folder_path} 資料夾裡面喔！")
except Exception as e:
    print(f"❌ 發生未知的錯誤：{e}")