import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz
import re
import time 

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

# ==============================================================================
# ===== ✨ TDX 金鑰 ✨ =====
# ==============================================================================
TDX_APP_ID = "t1190t-64266cda-41c7-451f"
TDX_APP_KEY = "0d5f5de8-ab0b-4d28-a573-92a3406c178c"
# ==============================================================================

CWA_API_KEY = os.environ.get('CWA_API_KEY', 'CWA-B3D5458A-4530-4045-A702-27A786C1E934')
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# ==============================================================================
# ===== ✨ 全域變數 ✨ =====
# ==============================================================================
cached_road_data = None
last_fetch_time = 0
CACHE_DURATION_SECONDS = 300

suhua_section_ids = []
# ==============================================================================


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

@app.get("/api/rainfall-map")
async def get_rainfall_map():
    image_url = "https://c1.1968services.tw/map-data/O-A0040-002.jpg"
    try:
        response = requests.get(image_url, timeout=10, verify=False)
        response.raise_for_status()
        return Response(content=response.content, media_type="image/jpeg")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rainfall map: {e}")
        return Response(status_code=404)

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
                first_forecast_pop = int(pop6h["time"][0]["parameter"]["parameterValue"])
                if first_forecast_pop <= 10:
                    forecasts[loc_name] = "無明顯降雨"
                else:
                    forecasts[loc_name] = f"{first_forecast_pop}% 機率降雨"
            else:
                forecasts[loc_name] = "預報資料異常"
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain forecast: {e}")
        for name in location_names.split(","):
            forecasts[name] = "預報讀取失敗"
    return forecasts

# ==============================================================================
# ===== ✨ 已按照您的指示修改 ✨ =====
# ==============================================================================
async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    # 按照使用者2025年7月31日 15:57 的最終指示進行修改
    station_ids = {
        "C0UB10": "蘇澳",
        "C0U760": "東澳",
        "C1U850": "南澳",
        "C0Z310": "清水斷崖",
        "C0TA50": "和仁",
        "C0Z180": "新城"
    }
    
    # 使用 O-A0001-001 資料集
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0001-001?Authorization={CWA_API_KEY}&stationId={','.join(station_ids.keys())}"
    
    # 預報功能地點未跟隨修改，可能造成部分預報無法匹配
    forecast_data = await get_cwa_rain_forecast()
    
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
                    "location": station_name, "mm": rain_value, "class": css_class,
                    "level": level_text, "time": obs_time,
                    "forecast": forecast_data.get(station_name, "預報讀取失敗")
                })
            else:
                processed_data.append({
                    "location": station_name, "mm": "N/A", "class": "rain-error", 
                    "level": "讀取失敗", "time": "", 
                    "forecast": forecast_data.get(station_name, "N/A")
                })

    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        for station_name in station_ids.values():
            processed_data.append({
                "location": station_name, "mm": "N/A", "class": "rain-error", 
                "level": "讀取失敗", "time": "", "forecast": "N/A"
            })
            
    return processed_data
# ==============================================================================

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
        if e.response and e.response.status_code == 404:
            pass
        else:
            print(f"Error fetching typhoon data: {e}")
    return None

def get_tdx_access_token():
    auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    body = {"grant_type": "client_credentials", "client_id": TDX_APP_ID, "client_secret": TDX_APP_KEY}
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        response = requests.post(auth_url, data=body, headers=headers)
        response.raise_for_status()
        token_data = response.json()
        print("✅ 成功獲取 TDX Access Token！")
        return token_data.get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"❌ 獲取 TDX Access Token 失敗: {e}")
        if e.response: print(f"    伺服器回應錯誤: {e.response.text}")
        return None

def fetch_and_cache_suhua_section_ids(access_token: str):
    global suhua_section_ids
    if suhua_section_ids:
        return

    print("🔍 首次執行，正在查詢蘇花路廊 SectionID...")
    sections_url = "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Section/Highway?$format=JSON"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    try:
        response = requests.get(sections_url, headers=headers, timeout=20)
        response.raise_for_status()
        all_sections = response.json().get("Sections", [])
        
        found_ids = [
            s["SectionID"] for s in all_sections 
            if s.get("RoadName") in ["台9線", "台9丁線"] and \
               ("澳" in s.get("SectionName", "") or \
                "花" in s.get("SectionName", "") or \
                "崇德" in s.get("SectionName", "") or \
                "和平" in s.get("SectionName", ""))
        ]
        
        suhua_section_ids = list(set(found_ids))
        print(f"🗺️ 成功找到 {len(suhua_section_ids)} 個蘇花路廊相關 SectionID 並已快取。")

    except requests.exceptions.RequestException as e:
        print(f"❌ 查詢 SectionID 失敗: {e}")


async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    global cached_road_data, last_fetch_time, suhua_section_ids

    current_time = time.time()
    if cached_road_data and (current_time - last_fetch_time < CACHE_DURATION_SECONDS):
        print("🔄 從快取中讀取路況資料...")
        return cached_road_data

    print("🚀 快取過期或不存在，重新從 TDX API 獲取資料...")
    
    sections = {
        "蘇澳-南澳": ["蘇澳", "東澳", "蘇澳隧道", "東澳隧道", "東岳隧道"],
        "南澳-和平": ["南澳", "武塔", "漢本", "和平", "觀音隧道", "谷風隧道"],
        "和平-秀林": ["和平", "和仁", "崇德", "秀林", "中仁隧道", "和平隧道", "和中隧道", "和中橋", "仁水隧道", "大清水隧道", "錦文隧道", "匯德隧道", "崇德隧道", "清水斷崖", "下清水橋", "大清水"]
    }
    high_risk_keywords = ["封閉", "中斷", "坍方"]
    downgrade_keywords = ["改道", "替代道路", "行駛台9丁線", "單線雙向", "戒護通行", "放行"]
    mid_risk_keywords = ["落石", "施工", "管制", "事故", "壅塞", "車多", "濃霧", "作業"]
    degree_keywords = ["單線", "單側", "車道", "非全路幅", "慢車道", "機動"]
    new_suhua_landmarks = ["蘇澳隧道", "東澳隧道", "觀音隧道", "谷風隧道", "中仁隧道", "仁水隧道"]
    new_suhua_km_ranges = [(104, 113), (124, 145), (148, 160)]

    results = {name: [] for name in sections.keys()}
    
    access_token = get_tdx_access_token()
    
    if not access_token:
        return results

    fetch_and_cache_suhua_section_ids(access_token)

    if not suhua_section_ids:
        print("⚠️ 未能獲取蘇花路廊的 SectionID，無法繼續查詢即時路況。")
        return results

    all_suhua_news = []
    for section_id in suhua_section_ids:
        live_news_url = f"https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Live/News/Highway/{section_id}?$top=5&$format=JSON"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = requests.get(live_news_url, headers=headers, timeout=5)
            if response.status_code == 200:
                all_suhua_news.extend(response.json().get("Newses", []))
            elif response.status_code != 204:
                response.raise_for_status()
        except requests.exceptions.RequestException:
            print(f"   - 查詢 SectionID {section_id} 時發生錯誤，已跳過。")
    
    print(f"✅ 成功從 {len(suhua_section_ids)} 個路段中，獲取到 {len(all_suhua_news)} 則路況消息。")
    
    unique_news = {news["NewsID"]: news for news in all_suhua_news}.values()

    for news in unique_news:
        title = news.get("Title", "")
        description = news.get("Description", "")
        full_content = f"{title}：{description}"
        if not description: continue

        time_str = news.get("StartTime", "")
        news_time = datetime.fromisoformat(time_str).astimezone(TAIPEI_TZ).strftime("%m/%d %H:%M") if time_str else "N/A"

        status_class = "status-low"
        if any(keyword in full_content for keyword in high_risk_keywords):
            status_class = "status-high"
        elif any(keyword in full_content for keyword in downgrade_keywords):
            status_class = "status-mid-alt"
        elif any(keyword in full_content for keyword in mid_risk_keywords):
            status_class = "status-mid"

        if "提醒" in title or "注意" in title:
            if status_class == "status-low": status_class = "status-mid"

        is_new_suhua = any(landmark in full_content for landmark in new_suhua_landmarks)
        km_match = re.search(r"(\d+(\.\d+)?)K", full_content, re.IGNORECASE)
        if km_match:
            km = float(km_match.group(1))
            if any(start <= km <= end for start, end in new_suhua_km_ranges):
                is_new_suhua = True

        road_type = "新蘇花" if is_new_suhua else "舊蘇花"

        news_item = {
            "time": news_time,
            "content": full_content,
            "status_class": status_class,
            "road_type": road_type
        }

        classified = False
        for section_name, keywords in sections.items():
            if any(keyword in full_content for keyword in keywords):
                results[section_name].append(news_item)
                classified = True
                break
        
        if not classified:
            if "蘇花" in full_content or "台9" in full_content:
                results[list(sections.keys())[1]].append(news_item)

    cached_road_data = results
    last_fetch_time = time.time()
    print("🔄 路況資料已更新至快取。")
            
    return results

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard FINAL VERSION is running."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
