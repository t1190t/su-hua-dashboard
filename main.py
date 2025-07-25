import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz
from bs4 import BeautifulSoup

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

# --- 資料獲取函式 ---
async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    # 更換為更穩定的鄉鎮觀測API (宜蘭縣、花蓮縣)
    location_names = "蘇澳鎮,南澳鄉,秀林鄉,新城鄉"
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091?Authorization={CWA_API_KEY}&locationName={location_names}"
    processed_data = []
    
    try:
        response = requests.get(url, verify=False, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        locations = data.get("records", {}).get("location", [])
        for loc in locations:
            station_name = loc.get("locationName")
            weather_elements = loc.get("weatherElement", [])
            
            # 找到24小時累積雨量(elementName 'PoP24h' or similar might not exist, we need to calculate it)
            # This API gives 3-hour forecasts. Let's find observed rainfall instead from O-A0001-001
            # Sticking to a simpler, more direct observation API is better. Reverting to O-A0001-001.
            
            # Let's use a new approach with a more reliable station data API
            station_obs_url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={CWA_API_KEY}&elementName=RAIN,HOUR_24"
            obs_response = requests.get(station_obs_url, verify=False, timeout=15)
            obs_response.raise_for_status()
            obs_data = obs_response.json()

            station_map = {"蘇澳鎮": "蘇澳", "南澳鄉": "南澳", "秀林鄉": "和中", "新城鄉": "新城"}
            target_stations = station_map.values()
            
            found_stations = {name: {} for name in location_names.split(',')}
            
            for station in obs_data.get("records", {}).get("location", []):
                s_name = station.get("locationName")
                if s_name in target_stations:
                    rain_value = float(next((el["weatherElement"][1].get("elementValue", "-1") for el in station["time"] if "weatherElement" in el and len(el["weatherElement"]) > 1), "-1"))
                    obs_time = datetime.fromisoformat(station["time"][0]["obsTime"]).astimezone(TAIPEI_TZ).strftime("%H:%M")
                    
                    # Map back to township name
                    for township, station_lookup in station_map.items():
                        if station_lookup == s_name:
                             found_stations[township] = {"rain": rain_value, "time": obs_time}

            for township, data in found_stations.items():
                if data:
                    level_text, css_class, _ = get_rain_level(data["rain"])
                    processed_data.append({
                        "location": township, "mm": data["rain"], "class": css_class,
                        "level": level_text, "time": data["time"]
                    })
                else:
                    processed_data.append({ "location": township, "mm": "N/A", "class": "rain-nodata", "level": "測站暫無回報", "time": "" })

    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        for station_name in location_names.split(','):
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
    # Plan B: 爬取警廣即時路況
    url = "https://www.1968services.tw/pbs-incident?region=e&page=1"
    sections = ["蘇澳-南澳", "南澳-和平", "和平-秀林"]
    results = {name: {"section": name, "status": "正常通行", "class": "road-green", "desc": "", "time": ""} for name in sections}
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        incidents = soup.find_all('div', class_='incident-item')
        update_time = datetime.now(TAIPEI_TZ).strftime("%H:%M")

        for incident in incidents:
            content = incident.get_text()
            if "台9線" in content or "蘇花" in content or "台9丁線" in content:
                # 簡單判斷影響的路段
                status = "事件"
                css_class = "road-red"
                if "坍方" in content: status = "坍方"
                elif "落石" in content: status = "落石"
                elif "施工" in content: status = "施工"; css_class = "road-yellow"
                elif "封閉" in content: status = "封閉"
                elif "事故" in content: status = "事故"

                if "蘇澳" in content or "東澳" in content:
                    results["蘇澳-南澳"]["status"] = status
                    results["蘇澳-南澳"]["class"] = css_class
                    results["蘇澳-南澳"]["desc"] = f"（{content.strip()}）"
                    results["蘇澳-南澳"]["time"] = update_time
                elif "南澳" in content or "和平" in content or "武塔" in content:
                    results["南澳-和平"]["status"] = status
                    results["南澳-和平"]["class"] = css_class
                    results["南澳-和平"]["desc"] = f"（{content.strip()}）"
                    results["南澳-和平"]["time"] = update_time
                elif "和平" in content or "崇德" in content or "清水" in content:
                    results["和平-秀林"]["status"] = status
                    results["和平-秀林"]["class"] = css_class
                    results["和平-秀林"]["desc"] = f"（{content.strip()}）"
                    results["和平-秀林"]["time"] = update_time

    except requests.exceptions.RequestException as e:
        print(f"Error fetching road data: {e}")
        for section_name in sections:
            results[section_name] = { "section": section_name, "status": "讀取失敗", "class": "road-red", "desc": "", "time": "" }
            
    return list(results.values())


@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard Backend is running with Final Fixes."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
