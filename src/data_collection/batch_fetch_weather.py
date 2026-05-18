import argparse
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 1. 基本設定與日誌初始化
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "denmark_weather_ALL.db"
LOG_FILE = BASE_DIR / "fetch_everything.log"
API_URL = "https://opendataapi.dmi.dk/v2/metObs/collections/observation/items"

# 🌟 API_KEY 記得填入 (如果原本是環境變數請自行替換)
API_KEY = "YOUR_API_KEY_HERE" 

# 🌟 核心修正：將切片改為小時制，預設 12 小時 (確保資料量低於 30 萬筆/區間)
DEFAULT_CHUNK_HOURS = 12 
PAGE_LIMIT = 10000
MAX_PAGE_RETRIES = 4
BACKOFF_BASE_SECONDS = 5
REQUEST_TIMEOUT = 60

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ==========================================
# 2. 網路請求穩定器
# ==========================================
def get_session():
    session = requests.Session()
    retry_kwargs = {
        'total': 5,
        'backoff_factor': 1,
        'status_forcelist': [429, 500, 502, 503, 504],
        'respect_retry_after_header': True,
    }
    try:
        retry = Retry(allowed_methods=frozenset(["HEAD", "GET", "OPTIONS"]), **retry_kwargs)
    except TypeError:
        retry = Retry(method_whitelist=frozenset(["HEAD", "GET", "OPTIONS"]), **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "LoadPulseBatchFetch/2.0"})
    return session

# ==========================================
# 3. 資料庫初始化與進度管理
# ==========================================
def init_db(reset=False):
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
        logging.info("🧹 已刪除舊資料庫，準備重新開始。")

    conn = sqlite3.connect(DB_PATH, timeout=30, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.execute('''
        CREATE TABLE IF NOT EXISTS weather_all (
            id TEXT PRIMARY KEY,
            station_id TEXT,
            parameter_id TEXT,
            observed_time TEXT,
            value REAL,
            longitude REAL,
            latitude REAL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_time ON weather_all (observed_time)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_station ON weather_all (station_id)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    return conn

def get_progress_time(conn):
    row = conn.execute("SELECT value FROM progress WHERE key = 'last_processed_time'").fetchone()
    if row:
        return datetime.fromisoformat(row[0])
    return None

def update_progress_time(conn, processed_time):
    conn.execute(
        "INSERT OR REPLACE INTO progress (key, value) VALUES ('last_processed_time', ?)",
        (processed_time.isoformat(),),
    )
    conn.commit()

# 🌟 修正切片邏輯：精確到小時
def generate_chunks(start_dt, end_dt, chunk_hours):
    cursor = start_dt
    while cursor <= end_dt:
        # 區間結束時間：加上指定小時，並減去一秒以避免重疊
        chunk_end = min(cursor + timedelta(hours=chunk_hours) - timedelta(seconds=1), end_dt)
        yield cursor, chunk_end
        cursor += timedelta(hours=chunk_hours)

def build_time_range(start_dt, end_dt):
    return f"{start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"

def insert_records(conn, records):
    before = conn.total_changes
    conn.executemany(
        '''
        INSERT OR IGNORE INTO weather_all
        (id, station_id, parameter_id, observed_time, value, longitude, latitude)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''',
        records,
    )
    conn.commit()
    return conn.total_changes - before

def fetch_page(session, url, params):
    response = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
    if response.status_code != 200:
        raise requests.HTTPError(f"{response.status_code} {response.reason}", response=response)
    return response.json()

# ==========================================
# 4. 分段下載與續跑主邏輯
# ==========================================
def process_chunk(conn, session, chunk_start, chunk_end):
    logging.info("⏳ 讀取區間 %s 到 %s", chunk_start.strftime('%Y-%m-%d %H:%M'), chunk_end.strftime('%Y-%m-%d %H:%M'))
    
    params = {
        "api-key": API_KEY, # 確保 API Key 有帶入
        "datetime": build_time_range(chunk_start, chunk_end), 
        "limit": PAGE_LIMIT
    }
    
    next_url = API_URL
    page = 1
    chunk_inserted = 0
    failed = False

    while next_url:
        page_retries = 0
        while page_retries < MAX_PAGE_RETRIES:
            try:
                # 只有第一頁需要塞 params，因為 next_url 已經包含了所有需要的 query strings
                payload = fetch_page(session, next_url, params if page == 1 else None)
                features = payload.get("features", [])
                
                if features:
                    records = []
                    for feature in features:
                        props = feature.get("properties", {})
                        coords = feature.get("geometry", {}).get("coordinates", [None, None])
                        records.append((
                            feature.get("id"),
                            props.get("stationId"),
                            props.get("parameterId"),
                            props.get("observed"),
                            props.get("value"),
                            coords[0] if len(coords) >= 2 else None,
                            coords[1] if len(coords) >= 2 else None,
                        ))
                    inserted = insert_records(conn, records)
                    chunk_inserted += inserted
                    logging.debug(" 📄 第 %d 頁寫入 %d 筆", page, inserted)

                next_url = None
                for link in payload.get("links", []):
                    if link.get("rel") == "next":
                        next_url = link.get("href")
                        break

                if next_url:
                    page += 1
                    time.sleep(0.2) # 稍微喘息，避免被 API 踢掉
                break
                
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response else None
                # 🌟 遇到 400 不再無腦重試，直接報錯跳出
                if status == 400:
                    logging.error("🔥 第 %d 頁收到 400 Bad Request。可能是分頁太深，考慮把 chunk_hours 調更小。URL: %s", page, next_url or API_URL)
                    failed = True
                    break
                elif status and status not in {429, 500, 502, 503, 504}:
                    logging.error("🔥 第 %d 頁收到 %d 客戶端錯誤：%s", page, status, exc)
                    failed = True
                    break
                
                # 針對 429 或 5xx 錯誤進行 Retry
                page_retries += 1
                wait = BACKOFF_BASE_SECONDS * page_retries
                logging.warning("⚠️ 伺服器繁忙 (狀態碼 %s)，重試 %d/%d，等待 %d 秒", status, page_retries, MAX_PAGE_RETRIES, wait)
                time.sleep(wait)
                
            except requests.RequestException as exc:
                page_retries += 1
                wait = BACKOFF_BASE_SECONDS * page_retries
                logging.warning("⚠️ 網路異常: %s，重試 %d/%d，等待 %d 秒", exc, page_retries, MAX_PAGE_RETRIES, wait)
                time.sleep(wait)

        else:
            logging.error("💀 區間第 %d 頁超過最大重試次數，宣告失敗。", page)
            failed = True
            break

    if failed:
        return False, 0

    logging.info("✅ 區間完成，共抓取 %d 頁，新增 %d 筆資料", page if not next_url else page-1, chunk_inserted)
    return True, chunk_inserted


def parse_datetime_start(value):
    return datetime.strptime(value, "%Y-%m-%d")

def parse_datetime_end(value):
    return datetime.strptime(value, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

def main():
    parser = argparse.ArgumentParser(description="安全、穩定地從 DMI 抓取天氣資料。")
    parser.add_argument("--start", default="2021-01-01", help="開始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="2025-12-31", help="結束日期 YYYY-MM-DD")
    parser.add_argument("--chunk-hours", type=int, default=DEFAULT_CHUNK_HOURS, help="每次抓取的區間(小時)，建議 12 或 24")
    parser.add_argument("--reset", action="store_true", help="刪除舊資料庫並重新抓取")
    parser.add_argument("--verbose", action="store_true", help="開啟除錯日誌(顯示每頁進度)")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    start_dt = parse_datetime_start(args.start)
    end_dt = parse_datetime_end(args.end)
    
    if start_dt > end_dt:
        parser.error("start 不能晚於 end")


    conn = init_db(reset=args.reset)
    saved_time = get_progress_time(conn)

    if saved_time and not args.reset:
        resume_time = saved_time + timedelta(seconds=1)
        if resume_time <= end_dt:
            if resume_time > start_dt:
                logging.info("⏱ 從已完成進度續跑：%s", resume_time.strftime('%Y-%m-%d %H:%M'))
                start_dt = resume_time
        else:
            logging.info("✅ 指定的時間區間已經全部下載完畢，無需執行。")
            conn.close()
            return

    session = get_session()
    total_inserted = 0
    total_chunks = 0

    for chunk_start, chunk_end in generate_chunks(start_dt, end_dt, args.chunk_hours):
        success, inserted = process_chunk(conn, session, chunk_start, chunk_end)
        total_chunks += 1
        if success:
            total_inserted += inserted
            update_progress_time(conn, chunk_end)
        else:
            logging.error("🛑 嚴重錯誤：區間 %s ~ %s 抓取失敗，程式終止，請檢查錯誤日誌。", chunk_start, chunk_end)
            break # 確保發生致命錯誤時停下來，而不是留下資料破洞繼續跑

    session.close()
    conn.close()

    logging.info("🏁 任務結束。共處理 %d 個區間，總計新增 %d 筆資料。", total_chunks, total_inserted)

if __name__ == "__main__":
    main()