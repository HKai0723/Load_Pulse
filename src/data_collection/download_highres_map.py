import requests
import os

# 1. 設定存檔路徑 (這次我們叫它 highres 高精度版)
save_dir = r"C:\school\Load_Pulse\Denmark\Geo"
geojson_path = os.path.join(save_dir, "denmark_regions_highres.geojson")

# 丹麥官方高精度地圖 API
url = "https://api.dataforsyningen.dk/regioner?format=geojson"

print("🌐 準備下載高精度官方地圖...")
print("💡 提示：因為檔案龐大，如果宿舍網路不穩失敗了，可以隨時重新執行。")

# 2. 開啟串流下載模式 (stream=True)
try:
    # stream=True 是關鍵，它讓 requests 不會急著把資料全抓下來
    with requests.get(url, stream=True, timeout=30) as response:
        # 檢查伺服器有沒有正常回應 (200 OK)
        response.raise_for_status() 
        
        print("連線成功！開始接收資料區塊...")
        
        # 'wb' 代表以二進位模式寫入 (Write Binary)，這對下載檔案最安全
        with open(geojson_path, 'wb') as f:
            downloaded_megabytes = 0
            
            # 每次只抓取 1MB (1024 * 1024 bytes) 的資料 (Chunking)
            for chunk in response.iter_content(chunk_size=1024*1024): 
                if chunk: # 如果這個區塊有東西
                    f.write(chunk)
                    downloaded_megabytes += 1
                    print(f"⬇️ 已安全寫入 {downloaded_megabytes} MB...")
                    
    print(f"\n✅ 恭喜！高精度地圖下載完成！")
    print(f"📂 檔案已妥善存至：{geojson_path}")

except requests.exceptions.RequestException as e:
    print(f"\n❌ 網路連線中斷或超時：{e}")
    print("沒關係，這通常是網路波動造成的，請回家用穩定的網路再試一次！")