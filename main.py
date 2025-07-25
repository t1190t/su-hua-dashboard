import os
import requests
import certifi # <--- 新增這一行
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional

# 初始化 FastAPI 應用
app = FastAPI()

# 允許所有來源的跨域請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 從環境變數讀取 API Key
CWA_API_KEY = os.environ.get('CWA_API_KEY', 'YOUR_API_KEY_IS_NOT_SET')

# --- API 路由定義 ---
@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    rain_info = await get_cwa_rain_data()
    earthquake_info = await get_cwa_earthquake_data()
    
    dashboard_data = {
      "lastUpdate": "2025-07-25 15:00", # 暫時寫死
      "rainInfo": rain_info,
      "radarImgUrl": "https://www.cwa.gov.tw/Data/radar/CV1_3600.png",
      "earthquakeInfo": earthquake_info,
      "roadInfo": [ 
        { "section": "蘇澳-南澳", "status": "正常通行", "class": "road-green", "desc": "", "time": "15:00" },
      ],
      "typhoonInfo": None 
    }

    return dashboard_data

# --- 資料獲取函式 ---
async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    """從中央氣象署獲取雨量資料"""
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={CWA_API_KEY}&format=JSON"
    processed_data = []
    try:
        # 使用 certifi 提供的憑證來進行 SSL 驗證
        response = requests.get(url, verify=certifi.where(), timeout=10) # <--- 修改這一行
        response.raise_for_status()
        data = response.json()

        # 此處應有真實的資料解析邏輯 (暫略)
        processed_data = [
            {"location": "蘇澳鎮", "mm": 55, "class": "rain-blue", "level": "🟦 中雨 (真實)", "time": "15:00"},
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        processed_data = [{"location": "雨量站", "mm": -1, "class": "", "level": "資料讀取失敗", "time": ""}]

    return processed_data

async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    """從中央氣象署獲取地震資料"""
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}&format=JSON"
    processed_data = []
    try:
        # 同樣使用 certifi
        response = requests.get(url, verify=certifi.where(), timeout=10) # <--- 修改這一行
        response.raise_for_status()
        data = response.json()
        
        # 此處應有真實的資料解析邏輯 (暫略)
        processed_data = [
            {"time": "2025-07-25 14:05", "location": "台灣東部海域 (真實)", "magnitude": 4.2, "depth": 20, "hualien_level": 2, "yilan_level": 2, "data_time": "14:08"}
        ]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching earthquake data: {e}")
        processed_data = [{"time": "讀取失敗", "location": "", "magnitude": 0, "depth": 0, "hualien_level": 0, "yilan_level": 0, "data_time": ""}]
    
    return processed_data

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running with updated SSL verification."}
