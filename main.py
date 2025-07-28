import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz
from bs4 import BeautifulSoup
import re

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
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# --- 【新增功能】除錯專用路由 ---
@app.get("/api/debug-road-html", response_class=Response)
async def debug_road_html():
    """
    這個路由的唯一功能，就是去爬取警廣網站，
    並將它看到的原始 HTML 內容，直接回傳給使用者。
    """
    url = "https://www.1968services.tw/pbs-incident?region=e&page=1"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        # 將網頁原始碼以純文字形式回傳
        return Response(content=response.text, media_type="text/plain; charset=utf-8")
    except requests.exceptions.RequestException as e:
        return Response(content=f"抓取 HTML 失敗: {e}", status_code=500)


# --- 原有功能 (暫時維持不變) ---
def get_rain_level(value: float) -> tuple[str, str, str]:
    if value < 0: return "資料異常", "rain-red", "資料異常"
    if value > 200: return "🟥 豪大雨", "rain-red", "豪大雨"
    if value > 130: return "🟧 豪雨", "rain-orange", "豪雨"
    if value > 80: return "🟨 大雨", "rain-yellow", "大雨"
    if value > 30: return "🟦 中雨", "rain-blue", "中雨"
    if value > 0: return "🟩 小雨", "rain-green", "小雨"
    return "⬜️ 無雨", "rain-none", "無雨"

@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    current_time = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    rain_info = await get_cwa_rain_data()
    earthquake_info = await get_cwa_earthquake_data()
    typhoon_info = await get_cwa_typhoon_data()
    road_info = await get_suhua_road_data()
    dashboard_data = {
      "lastUpdate": current_time, "rainInfo": rain_info, "earthquakeInfo": earthquake_info,
      "roadInfo": road_info, "typhoonInfo": typhoon_info
    }
    return dashboard_data

@app.get("/api/radar-image")
async def get_radar_image():
    image_url = "https://www.cwa.gov.tw/Data/radar/CV1_3600.png"
    try:
        response = requests.get(image_url, timeout=10, verify=False)
        response.raise_for_status()
        return Response(content=response.content, media_type="image/png")
    except requests.exceptions.RequestException as e: return Response(status_code=404)

@app.get("/api/rainfall-map")
async def get_rainfall_map():
    image_url = "https://c1.1968services.tw/map-data/O-A0040-002.jpg"
    try:
        response = requests.get(image_url, timeout=10, verify=False)
        response.raise_for_status()
        return Response(content=response.content, media_type="image/jpeg")
    except requests.exceptions.RequestException as e: return Response(status_code=404)

async def get_cwa_rain_forecast() -> Dict[str, str]:
    location_names = "蘇澳鎮,南澳鄉,秀林鄉,新城鄉"
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091?Authorization={CWA_API_KEY}&locationName={location_names}&elementName=PoP6h"
    forecasts = {}
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        locations = data.get("records", {}).get("location", [])
        for loc in locations:
            loc_name = loc.get("locationName")
            weather_elements = loc.get("weatherElement", [])
            pop6h = next((el for el in weather_elements if el.get("elementName") == "PoP6h"), None)
            if pop6h and pop6h.get("time"):
                forecasts[loc_name] = f"{int(pop6h['time'][0]['parameter']['parameterValue'])}% 機率降雨" if int(pop6h['time'][0]['parameter']['parameterValue']) > 10 else "無明顯降雨"
            else: forecasts[loc_name] = "預報資料異常"
    except requests.exceptions.RequestException as e:
        for name in location_names.split(","): forecasts[name] = "預報讀取失敗"
    return forecasts

async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    # This function remains as is, but the content is omitted here for brevity
    # It will be included in the final copy-paste
    station_ids = {"C0O920": "蘇澳鎮", "C0U9N0": "南澳鄉", "C0Z030": "秀林鄉", "C0T8A0":"新城鄉"}
    forecast_data = await get_cwa_rain_forecast()
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001?Authorization={CWA_API_KEY}&stationId={','.join(station_ids.keys())}"
    processed_data = []
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        stations_data = {station["stationId"]: station for station in data.get("records", {}).get("location", [])}
        for station_id, station_name in station_ids.items():
            station = stations_data.get(station_id)
            if station:
                rain_value_str = next((item["elementValue"] for item in station["weatherElement"] if item["elementName"] == "HOUR_24"), "0")
                rain_value = float(rain_value_str)
                obs_time = datetime.fromisoformat(station["time"]["obsTime"]).astimezone(TAIPEI_TZ).strftime("%H:%M")
                level_text, css_class, _ = get_rain_level(rain_value)
                processed_data.append({
                    "location": station_name, "mm": rain_value, "class": css_class, "level": level_text, "time": obs_time,
                    "forecast": forecast_data.get(station_name, "預報讀取失敗")
                })
            else:
                processed_data.append({ "location": station_name, "mm": "N/A", "class": "rain-nodata", "level": "測站暫無回報", "time": "", "forecast": forecast_data.get(station_name, "N/A") })
    except requests.exceptions.RequestException as e:
        for station_name in station_ids.values():
             processed_data.append({"location": station_name, "mm": "N/A", "class": "rain-error", "level": "讀取失敗", "time": "", "forecast": "N/A"})
    return processed_data

async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    # This function remains as is, but the content is omitted here for brevity
    return []

async def get_cwa_typhoon_data() -> Optional[Dict[str, Any]]:
    # This function remains as is, but the content is omitted here for brevity
    return None

async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    # This is the failing function. It will return the default for now.
    sections = {
        "蘇澳-南澳": [], "南澳-和平": [], "和平-秀林": []
    }
    return sections

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard DEBUGGER is running."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
