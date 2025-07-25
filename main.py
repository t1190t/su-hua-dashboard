import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional

# 初始化 FastAPI 應用
app = FastAPI()

# 允許所有來源的跨域請求，這樣 Vercel 上的前端才能跟 Render 上的後端溝通
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在正式產品中，這裡應該只填寫您的 Vercel 網址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 從環境變數讀取 API Key，這是安全作法
# 在 Render 上設定時，我們會把您的 Key 存在這裡
CWA_API_KEY = os.environ.get('CWA_API_KEY', 'YOUR_API_KEY_IS_NOT_SET')

# --- API 路由定義 ---
@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    """
    這是我們唯一的 API 端點，它會獲取所有需要的資料並回傳。
    """
    # 1. 獲取氣象局資料
    rain_info = await get_cwa_rain_data()
    earthquake_info = await get_cwa_earthquake_data()
    
    # 2. (待辦) 獲取蘇花路況資料
    # road_info = await get_suhua_road_data() 

    # 3. 組合所有資料
    dashboard_data = {
      "lastUpdate": "2025-07-25 14:30", # 暫時寫死
      "rainInfo": rain_info,
      "radarImgUrl": "https://www.cwa.gov.tw/Data/radar/CV1_3600.png",
      "earthquakeInfo": earthquake_info,
      "roadInfo": [ # 暫時使用假資料
        { "section": "蘇澳-南澳", "status": "正常通行", "class": "road-green", "desc": "", "time": "14:30" },
        { "section": "南澳-和平", "status": "查詢中...", "class": "road-yellow", "desc": "", "time": "14:30" }
      ],
      "typhoonInfo": None # 暫時使用假資料
    }

    return dashboard_data

# --- 資料獲取函式 ---
async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    """從中央氣象署獲取雨量資料"""
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={CWA_API_KEY}&format=JSON"
    processed_data = []
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status() # 如果請求失敗，會拋出異常
        data = response.json()

        # 在這裡加上解析 JSON 並轉換成我們前端需要格式的程式碼
        # ... 為了簡化，此處暫時返回假資料，但 API 呼叫是真的
        processed_data = [
            {"location": "蘇澳鎮", "mm": 55, "class": "rain-blue", "level": "🟦 中雨", "time": "14:30"},
            {"location": "南澳鄉", "mm": 82, "class": "rain-yellow", "level": "🟨 大雨", "time": "14:30"}
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        # 如果 API 失敗，返回一個錯誤訊息
        processed_data = [{"location": "雨量站", "mm": -1, "class": "", "level": "資料讀取失敗", "time": ""}]

    return processed_data

async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    """從中央氣象署獲取地震資料"""
    # ... 此處應有類似的 requests.get() 呼叫
    # 為了簡化，暫時返回假資料
    return [
        {"time": "2025-07-25 14:05", "location": "台灣東部海域", "magnitude": 4.2, "depth": 20, "hualien_level": 2, "yilan_level": 2, "data_time": "14:08"}
    ]

# 根路由，可以用來檢查服務是否正常啟動
@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running."}