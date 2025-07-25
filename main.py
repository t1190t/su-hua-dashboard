import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings

# 忽略 InsecureRequestWarning 警告
from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

# 初始化 FastAPI 應用
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
      "earthquakeInfo": earthquake_info,
      "roadInfo": road_info,
      "typhoonInfo": typhoon_info
    }
    return dashboard_data

@app.get("/api/radar-image")
async def get_radar_image():
    image_url = "https://www.cwa.gov.tw/Data/radar/CV1_3600.png"
    try:
        response = requests.get(image_url, timeout=10, verify=False)
        response.raise_for_status()
        return Response(content=response.content, media_type="image/png")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching radar image: {e}")
        return Response(status_code=404)

# --- 資料獲取函式 ---
async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    station_ids = {"C0O920": "蘇澳鎮", "C0U9N0": "南澳鄉", "C0Z030": "秀林鄉", "C0T8A0":"新城鄉"}
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={CWA_API_KEY}&stationId={','.join(station_ids.keys())}"
    processed_data = []
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # 建立一個測站資料的字典方便查找
        stations_data = {station["stationId"]: station for station in data.get("records", {}).get("location", [])}
        
        # 依我們指定的順序來處理，確保每個測站都有顯示
        for station_id, station_name in station_ids.items():
            station = stations_data.get(station_id)
            if station:
                rain_value_str = next((item["elementValue"] for item in station["weatherElement"] if item["elementName"] == "HOUR_24"), "-1")
                rain_value = float(rain_value_str)
                obs_time = datetime.fromisoformat(station["time"]["obsTime"]).strftime("%H:%M")
                level_text, css_class, _ = get_rain_level(rain_value)
                processed_data.append({
                    "location": station_name, "mm": rain_value, "class": css_class,
                    "level": level_text, "time": obs_time
                })
            else:
                processed_data.append({
                    "location": station_name, "mm": -1, "class": "rain-red",
                    "level": "暫無資料", "time": ""
                })

    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        for station_name in station_ids.values():
             processed_data.append({"location": station_name, "mm": -1, "class": "", "level": "讀取失敗", "time": ""})
    return processed_data

async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    # 請求最近30筆地震，以確保涵蓋三天內的資料
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}&limit=30"
    processed_data = []
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("records") and data["records"].get("Earthquake"):
            three_days_ago = datetime.now() - timedelta(days=3)
            for quake in data["records"]["Earthquake"]:
                earthquake_info = quake.get("EarthquakeInfo", {})
                
                quake_time_str = earthquake_info.get("OriginTime")
                if not quake_time_str: continue

                quake_time = datetime.fromisoformat(quake_time_str)
                
                # 只處理三天內的地震
                if quake_time >= three_days_ago:
                    epicenter = earthquake_info.get("Epicenter", {})
                    magnitude_info = earthquake_info.get("Magnitude", {})
                    magnitude_value = magnitude_info.get("MagnitudeValue", 0)
                    report_content = quake.get("ReportContent", "")
                    report_time_str = ""
                    if isinstance(report_content, dict):
                        report_time_str = report_content.get("web", "")
                    report_time = datetime.fromisoformat(report_time_str).strftime("%H:%M") if report_time_str else ""
                    
                    yilan_level = "0"
                    hualien_level = "0"
                    for area in quake.get("Intensity", {}).get("ShakingArea", []):
                        if area.get("AreaDesc") == "宜蘭縣": yilan_level = area.get("AreaIntensity", "0")
                        if area.get("AreaDesc") == "花蓮縣": hualien_level = area.get("AreaIntensity", "0")

                    processed_data.append({
                        "time": quake_time.strftime("%Y-%m-%d %H:%M"), "location": epicenter.get("Location", "不明"),
                        "magnitude": magnitude_value, "depth": earthquake_info.get("FocalDepth", 0),
                        "hualien_level": hualien_level.replace("級", ""), "yilan_level": yilan_level.replace("級", ""),
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
        if data.get("records") and data["records"].get("sea_typhoon_warning"):
             typhoon_warnings = data["records"]["sea_typhoon_warning"].get("typhoon_warning_summary",{}).get("SeaTyphoonWarning")
             if typhoon_warnings:
                typhoon = typhoon_warnings[0]
                update_time = datetime.fromisoformat(typhoon["issue_time"]).strftime("%H:%M")
                return {
                    "name": typhoon["typhoon_name"], "warning_type": typhoon["warning_type"],
                    "update_time": update_time, "location": typhoon["center_location"],
                    "wind_speed": typhoon["max_wind_speed"], "status": typhoon["warning_summary"]["content"],
                    "img_url": "https://www.cwa.gov.tw/Data/typhoon/TY_NEWS/TY_NEWS_0.jpg"
                }
    except requests.exceptions.RequestException as e:
        # 如果錯誤是 404 Not Found，代表沒有颱風，這是正常情況，不用印出錯誤
        if e.response and e.response.status_code == 404:
            print("No active typhoon warning found (404). This is normal.")
        else:
            print(f"Error fetching typhoon data: {e}")
    return None

async def get_suhua_road_data() -> List[Dict[str, Any]]:
    # 下一步開發的重點
    return [
        {"section": "蘇澳-南澳", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
        {"section": "南澳-和平", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
        {"section": "和平-秀林", "status": "待查詢...", "class": "road-yellow", "desc": "（正在開發此功能）", "time": ""},
    ]

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running with optimized data fetching."}
