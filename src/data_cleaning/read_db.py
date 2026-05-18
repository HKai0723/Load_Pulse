import sqlite3
import pandas as pd

# 1. 設定資料庫路徑 
# 請將這裡替換成你檔案總管上方網址列的完整路徑 + \TE.db
# 例如: r"\\100.89.150.54\loadpulse\load_pulse\te_project_test\database\TE.db"
db_path = r"\\100.89.150.54\CWA_project\load_pulse.db"

try:
    # 2. 建立連線
    conn = sqlite3.connect(db_path)
    print("✅ 成功連線到 TE.db！")
    
    # 3. 查詢這個資料庫裡所有的「資料表名稱」
    query_tables = "SELECT name FROM sqlite_master WHERE type='table';"
    tables = pd.read_sql_query(query_tables, conn)
    
    print("\n🔍 資料庫內包含以下資料表：")
    print(tables)
    
except Exception as e:
    print(f"❌ 發生錯誤: {e}")
finally:
    # 確保最後有把連線關閉
    if 'conn' in locals():
        conn.close()