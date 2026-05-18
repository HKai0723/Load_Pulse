import pandas as pd
import numpy as np
import logging
import os

# 1. 設定路徑
csv_path = r"C:\school\Load_Pulse\Denmark\Clean_Consumption_Wide.csv"
log_path = r"C:\school\Load_Pulse\Denmark\clean\anomaly_report.log"
time_col = "TimeUTC"

# 2. 設定專業的 Logging 系統
# 這樣設定可以讓訊息同時寫入檔案，並顯示在 VS Code 的終端機裡
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8', mode='w'), # 'w' 代表每次跑都會覆蓋舊的 log，若要累加請改成 'a'
        logging.StreamHandler()
    ]
)

def check_data_anomalies(file_path, time_col):
    logging.info(f"🏥 開始執行數值異常體檢...")
    logging.info(f"📂 讀取檔案：{file_path}")
    
    df = pd.read_csv(file_path)
    df[time_col] = pd.to_datetime(df[time_col])
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    total_issues = 0

    for col in numeric_cols:
        logging.info(f"--- 📊 檢測地區：{col} ---")
        col_issues = 0
        
        # A. 負數檢查
        neg_df = df[df[col] < 0]
        if len(neg_df) > 0:
            logging.error(f"發現 {len(neg_df)} 筆負數用電量！")
            col_issues += 1
            
        # B. 零值檢查
        zero_df = df[df[col] == 0]
        if len(zero_df) > 0:
            logging.warning(f"發現 {len(zero_df)} 筆用電量為 0！")
            col_issues += 1
            
        # C. 感測器卡死檢查
        stuck_mask = (df[col].diff() == 0) & (df[col] != 0)
        if stuck_mask.sum() > 0:
            logging.warning(f"發現 {stuck_mask.sum()} 筆連續重複數值 (感測器疑似卡死)！")
            col_issues += 1
            
        # D. 統計極端值 (大於 3 倍標準差)
        mean_val = df[col].mean()
        std_val = df[col].std()
        outliers = df[(df[col] - mean_val).abs() > 3 * std_val]
        
        if len(outliers) > 0:
            logging.info(f"發現 {len(outliers)} 筆超過 3 倍標準差的極端值 (可能是真實氣候影響)。")
            logging.info(f"    -> 該區 Max: {df[col].max():,.2f} | Min: {df[col].min():,.2f} | Mean: {mean_val:,.2f}")
            col_issues += 1
            
        if col_issues == 0:
            logging.info("狀態：完美，無明顯異常。")
        
        total_issues += col_issues

    logging.info("="*50)
    if total_issues == 0:
        logging.info("🎉 體檢完成：全區資料數值完美，沒有發現基礎異常地雷！")
    else:
        logging.warning(f"🛠️ 體檢完成：共發現了潛在異常狀況，請查閱上方紀錄進行後續插值或保留評估。")

if __name__ == "__main__":
    check_data_anomalies(csv_path, time_col)