import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz

from urllib3.exceptions import InsecureRequestWarning
warnings.simplefilter('ignore', InsecureRequestWarning)

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

async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    station_ids = {"C0O920": "蘇澳鎮", "C0U9N0": "南澳鄉", "C0Z030": "秀林鄉", "C0T8A0":"新城鄉"}
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
                rain_value_str = next((item["elementValue"] for item in station["weatherElement"] if item["elementName"] == "HOUR_24"), "-1")
                rain_value = float(rain_value_str)
                obs_time = datetime.fromisoformat(station["time"]["obsTime"]).astimezone(TAIPEI_TZ).strftime("%H:%M")
                level_text, css_class, _ = get_rain_level(rain_value)
                processed_data.append({
                    "location": station_name, "mm": rain_value, "class": css_class,
                    "level": level_text, "time": obs_time
                })
            else:
                processed_data.append({ "location": station_name, "mm": "N/A", "class": "rain-nodata", "level": "測站暫無回報", "time": "" })
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        for station_name in station_ids.values():
             processed_data.append({"location": station_name, "mm": "N/A", "class": "rain-error", "level": "讀取失敗", "time": ""})
    return processed_data

async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001?Authorization={CWA_API_KEY}&limit=30"
    processed_data = []
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("records") and data["records"].get("Earthquake"):
            three_days_ago = datetime.now(TAIPEI_TZ) - timedelta(days=3)
            for quake in data["records"]["Earthquake"]:
                earthquake_info = quake.get("EarthquakeInfo", {})
                quake_time_str = earthquake_info.get("OriginTime")
                if not quake_time_str: continue
                quake_time = datetime.fromisoformat(quake_time_str).astimezone(TAIPEI_TZ)
                if quake_time >= three_days_ago:
                    yilan_level_str = "0"; hualien_level_str = "0"
                    for area in quake.get("Intensity", {}).get("ShakingArea", []):
                        if area.get("AreaDesc") == "宜蘭縣": yilan_level_str = area.get("AreaIntensity", "0")
                        if area.get("AreaDesc") == "花蓮縣": hualien_level_str = area.get("AreaIntensity", "0")
                    try:
                        yilan_level_int = int(yilan_level_str.replace("級", "")); hualien_level_int = int(hualien_level_str.replace("級", ""))
                    except ValueError:
                        yilan_level_int = 0; hualien_level_int = 0
                    if yilan_level_int >= 2 or hualien_level_int >= 2:
                        epicenter = earthquake_info.get("Epicenter", {})
                        magnitude_info = earthquake_info.get("Magnitude", {})
                        magnitude_value = magnitude_info.get("MagnitudeValue", 0)
                        report_content = quake.get("ReportContent", "")
                        report_time_str = ""
                        if isinstance(report_content, dict): report_time_str = report_content.get("web", "")
                        report_time = datetime.fromisoformat(report_time_str).astimezone(TAIPEI_TZ).strftime("%H:%M") if report_time_str else ""
                        processed_data.append({
                            "time": quake_time.strftime("%Y-%m-%d %H:%M"), "location": epicenter.get("Location", "不明"),
                            "magnitude": magnitude_value, "depth": earthquake_info.get("FocalDepth", 0),
                            "hualien_level": str(hualien_level_int), "yilan_level": str(yilan_level_int),
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
                update_time = datetime.fromisoformat(typhoon["issue_time"]).astimezone(TAIPEI_TZ).strftime("%H:%M")
                return {
                    "name": typhoon["typhoon_name"], "warning_type": typhoon["warning_type"],
                    "update_time": update_time, "location": typhoon["center_location"],
                    "wind_speed": typhoon["max_wind_speed"], "status": typhoon["warning_summary"]["content"],
                    "img_url": "https://www.cwa.gov.tw/Data/typhoon/TY_NEWS/TY_NEWS_0.jpg"
                }
    except requests.exceptions.RequestException as e:
        if e.response and e.response.status_code == 404: pass
        else: print(f"Error fetching typhoon data: {e}")
    return None

async def get_suhua_road_data() -> List[Dict[str, Any]]:
    sections = { "S00111": "蘇澳-南澳", "S00112": "南澳-和平", "S00113": "和平-秀林" }
    url = "https://168.thb.gov.tw/api/thb/section/status/GROUP/L2"
    results = {name: {"section": name, "status": "正常通行", "class": "road-green", "desc": "", "time": ""} for name in sections.values()}
    try:
        # 【修改處】加上 verify=False 來解決 SSL 錯誤
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
        update_time = datetime.now(TAIPEI_TZ).strftime("%H:%M")
        if data.get("features"):
            for event in data["features"]:
                props = event.get("properties", {})
                section_id = props.get("section_id")
                if section_id in sections:
                    section_name = sections[section_id]
                    event_type = props.get("event_type", "不明事件")
                    description = props.get("description", "")
                    results[section_name]["status"] = event_type
                    results[section_name]["class"] = "road-red"
                    results[section_name]["desc"] = f"（{description}）"
                    results[section_name]["time"] = update_time
    except requests.exceptions.RequestException as e:
        print(f"Error fetching road data: {e}")
        for section_name in sections.values():
            results[section_name] = { "section": section_name, "status": "讀取失敗", "class": "road-red", "desc": "", "time": "" }
    return list(results.values())

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running with Final Fixes."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
