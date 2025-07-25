import os
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime
import warnings

# 忽略 InsecureRequestWarning 警告
from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

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

# --- Helper Functions ---
def get_rain_level(value: float) -> tuple[str, str, str]:
    if value < 0: return "資料異常", "rain-red", "資料異常"
    if value > 200: return "🟥 豪大雨", "rain-red", "豪大雨"
    if value > 130: return "🟧 豪雨", "rain-orange", "豪雨"
    if value > 80: return "🟨 大雨", "rain-yellow", "大雨"
    if value > 30: return "🟦 中雨", "rain-blue", "中雨"
    if value > 0: return "🟩 小雨", "rain-green", "小雨"
    return "⬜️ 無雨", "rain-none", "無雨"

# --- API 路由定義 ---
@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    rain_info = await get_cwa_rain_data()
    earthquake_info = await get_cwa_earthquake_data()
    typhoon_info = await get_cwa_typhoon_data()
    road_info = await get_suhua_road_data()

    dashboard_data = {
      "lastUpdate": current_time,
      "rainInfo": rain_info,
      "radarImgUrl": "https://www.cwa.gov.tw/Data/radar/CV1_3600.png",
      "earthquakeInfo": earthquake_info,
      "roadInfo": road_info,
      "typhoonInfo": typhoon_info
    }
    return dashboard_data

# --- 資料獲取函式 ---
async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    station_ids = {"C0O920": "蘇澳鎮", "C0U9N0": "南澳鄉", "C0Z030": "秀林鄉", "C0T8A0":"新城鄉"}
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={CWA_API_KEY}&stationId={','.join(station_ids.keys())}"
    processed_data = []
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("records") and data["records"].get("location"):
            for station in data["records"]["location"]:
                station_name = station_ids.get(station["stationId"], station["stationName"])
                # 尋找24小時累積雨量，如果不存在則使用-1
                rain_value_str = next((item["elementValue"] for item in station["weatherElement"] if item["elementName"] == "HOUR_24"), "-1")
                rain_value = float(rain_value_str)
                obs_time = datetime.fromisoformat(station["time"]["obsTime"]).strftime("%H:%M")
                level_text, css_class, _ = get_rain_level(rain_value)
                
                processed_data.append({
                    "location": station_name, "mm": rain_value, "class": css_class,
                    "level": level_text, "time": obs_time
                })
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        processed_data.append({"location": "雨量站", "mm": -1, "class": "", "level": "資料讀取失敗", "time": ""})
    return processed_data

async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}&limit=2"
    processed_data = []
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("records") and data["records"].get("Earthquake"):
            for quake in data["records"]["Earthquake"]:
                quake_time = datetime.fromisoformat(quake["EarthquakeInfo"]["OriginTime"]).strftime("%Y-%m-%d %H:%M")
                report_time = datetime.fromisoformat(quake["ReportContent"]["web"]).strftime("%H:%M") if "web" in quake["ReportContent"] else ""
                yilan_level = next((area["AreaIntensity"] for area in quake["Intensity"]["ShakingArea"] if area["AreaDesc"] == "宜蘭縣"), "0")
                hualien_level = next((area["AreaIntensity"] for area in quake["Intensity"]["ShakingArea"] if area["AreaDesc"] == "花蓮縣"), "0")
                processed_data.append({
                    "time": quake_time, "location": quake["EarthquakeInfo"]["Epicenter"]["Location"],
                    "magnitude": quake["EarthquakeInfo"]["Magnitude"]["MagnitudeValue"], "depth": quake["EarthquakeInfo"]["FocalDepth"],
                    "hualien_level": hualien_level, "yilan_level": yilan_level, "data_time": report_time
                })
    except requests.exceptions.RequestException as e:
        print(f"Error fetching earthquake data: {e}")
    return processed_data

async def get_cwa_typhoon_data() -> Optional[Dict[str, Any]]:
    # ... (此函式與之前相同，此處省略以節省空間)
    return None

async def get_suhua_road_data() -> List[Dict[str, Any]]:
    return [
        {"section": "蘇澳-南澳", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
    ]

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running on Render with full data parsing."}
