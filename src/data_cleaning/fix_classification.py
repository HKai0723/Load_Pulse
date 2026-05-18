import pandas as pd
from pathlib import Path

# 路徑設定
BASE_DIR = Path(__file__).resolve().parent
# 讀取你一開始抓下來的最原始名冊 (含有 validFrom 和 validTo)
RAW_CSV = BASE_DIR / "denmark_stations_info.csv" 
# 我們要覆蓋掉昨天那份錯誤的分類表
OUTPUT_CSV = BASE_DIR / "stations_classified.csv"

def fix_classification():
    print("🛠️ 正在修復分類邏輯 Bug...")
    
    if not RAW_CSV.exists():
        print(f"❌ 找不到原始檔案 {RAW_CSV.name}")
        return
        
    df = pd.read_csv(RAW_CSV)

    # 1. 終極日期轉換：強制轉型，並把時區拔掉 (tz_localize(None)) 避免比較衝突
    df['start_dt'] = pd.to_datetime(df['validFrom'], errors='coerce').dt.tz_localize(None)
    df['end_dt'] = pd.to_datetime(df['validTo'], errors='coerce').dt.tz_localize(None)

    # 2. 嚴謹的生命週期判斷邏輯
    def get_lifecycle(row):
        start = row['start_dt']
        end = row['end_dt']
        baseline_2021 = pd.Timestamp('2021-01-01')

        # 如果結束時間是 NaT (空值)，代表他『還活著』
        if pd.isna(end):
            # 只要沒有開始時間，或者開始時間早於 2021，就是老油條
            if pd.isna(start) or start < baseline_2021:
                return '2021前活到現在'
            else:
                return '2021~2025新增'
                
        # 如果有結束時間，代表他『已經死亡』
        else:
            if end < baseline_2021:
                return '2021前已死亡'
            else:
                return '2021~2025死亡'

    # 3. 套用新邏輯
    df['生命週期'] = df.apply(get_lifecycle, axis=1)
    
    # 4. 更新狀態顯示 (地圖上的文字)
    df['狀態'] = df['end_dt'].apply(lambda x: "運作中" if pd.isna(x) else str(x.date()))

    # 5. 整理欄位並存檔 (覆蓋掉有 Bug 的舊版)
    cols = ['測站ID', '站名', '所屬區域', '生命週期', '狀態', '緯度', '經度']
    # 確保欄位都存在才篩選
    existing_cols = [c for c in cols if c in df.columns]
    
    df[existing_cols].to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"✅ 修復完成！已成功覆蓋 {OUTPUT_CSV.name}")
    
    # 偷偷印出統計結果讓你安心
    print("\n📊 修正後的測站生命週期統計：")
    print(df['生命週期'].value_counts().to_string())

if __name__ == "__main__":
    fix_classification()