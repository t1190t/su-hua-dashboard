import os
import requests
import certifi
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime

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
    if value > 200:
        return "🟥 豪大雨", "rain-red", "豪大雨"
    if value > 130:
        return "🟧 豪雨", "rain-orange", "豪雨"
    if value > 80:
        return "🟨 大雨", "rain-yellow", "大雨"
    if value > 30:
        return "🟦 中雨", "rain-blue", "中雨"
    if value > 0:
        return "🟩 小雨", "rain-green", "小雨"
    return "⬜️ 無雨", "rain-none", "無雨"

# --- API 路由定義 ---
@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 平行獲取所有資料
    rain_info = await get_cwa_rain_data()
    earthquake_info = await get_cwa_earthquake_data()
    typhoon_info = await get_cwa_typhoon_data()
    road_info = await get_suhua_road_data() # (目前仍為假資料)

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
    # 我們關心的測站ID
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
                rain_value = float(station["weatherElement"][1]["elementValue"]) # 24小時累積雨量
                obs_time = datetime.fromisoformat(station["time"]["obsTime"]).strftime("%H:%M")
                
                level_text, css_class, _ = get_rain_level(rain_value)
                
                processed_data.append({
                    "location": station_name,
                    "mm": rain_value,
                    "class": css_class,
                    "level": level_text,
                    "time": obs_time
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
                quake_time = datetime.fromisoformat(quake["EarthquakeInfo"]["OriginTime"]).strftime("%Y-%m-%d %H:%M:%S")
                report_time = datetime.fromisoformat(quake["ReportContent"]["web"]).strftime("%H:%M") if "web" in quake["ReportContent"] else ""
                
                # 取得各地震度
                yilan_level = "0"
                hualien_level = "0"
                for area in quake["Intensity"]["ShakingArea"]:
                    if area["AreaDesc"] == "宜蘭縣":
                        yilan_level = area["AreaIntensity"]
                    if area["AreaDesc"] == "花蓮縣":
                        hualien_level = area["AreaIntensity"]

                processed_data.append({
                    "time": quake_time,
                    "location": quake["EarthquakeInfo"]["Epicenter"]["Location"],
                    "magnitude": quake["EarthquakeInfo"]["Magnitude"]["MagnitudeValue"],
                    "depth": quake["EarthquakeInfo"]["FocalDepth"],
                    "hualien_level": hualien_level,
                    "yilan_level": yilan_level,
                    "data_time": report_time
                })
    except requests.exceptions.RequestException as e:
        print(f"Error fetching earthquake data: {e}")
    return processed_data

async def get_cwa_typhoon_data() -> Optional[Dict[str, Any]]:
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/T-A0001-001?Authorization={CWA_API_KEY}"
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("records") and data["records"].get("sea_typhoon_warning") and data["records"]["sea_typhoon_warning"]["typhoon_warning_summary"]:
            typhoon = data["records"]["sea_typhoon_warning"]["typhoon_warning_summary"]["SeaTyphoonWarning"][0]
            update_time = datetime.fromisoformat(typhoon["issue_time"]).strftime("%H:%M")
            return {
                "name": typhoon["typhoon_name"],
                "warning_type": typhoon["warning_type"],
                "update_time": update_time,
                "location": typhoon["center_location"],
                "wind_speed": typhoon["max_wind_speed"],
                "status": typhoon["warning_summary"]["content"],
                "img_url": "https://www.cwa.gov.tw/Data/typhoon/TY_NEWS/TY_NEWS_0.jpg" # URL是固定的
            }
    except requests.exceptions.RequestException as e:
        print(f"Error fetching typhoon data: {e}")
    return None # 沒有颱風或API失敗時返回 None

async def get_suhua_road_data() -> List[Dict[str, Any]]:
    # 這是我們下一步要開發的功能，目前先回傳假資料
    return [
        {"section": "蘇澳-南澳", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
        {"section": "南澳-和平", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
        {"section": "和平-秀林", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
    ]

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running with full data parsing."}
