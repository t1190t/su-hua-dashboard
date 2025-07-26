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

# --- 資料獲取函式 ---
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

async def get_cwa_rain_data() -> List[Dict[str, Any]]:
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
                    "location": station_name, "mm": rain_value, "class": css_class,
                    "level": level_text, "time": obs_time,
                    "forecast": forecast_data.get(station_name, "預報讀取失敗")
                })
            else:
                processed_data.append({ "location": station_name, "mm": "N/A", "class": "rain-nodata", "level": "測站暫無回報", "time": "", "forecast": forecast_data.get(station_name, "N/A") })
    except requests.exceptions.RequestException as e:
        print(f"Error fetching rain data: {e}")
        for station_name in station_ids.values():
             processed_data.append({"location": station_name, "mm": "N/A", "class": "rain-error", "level": "讀取失敗", "time": "", "forecast": "N/A"})
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

async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    base_url = "https://www.1968services.tw/pbs-incident?region=e&page="
    pages_to_scrape = [1, 2]
    
    sections = {
        "蘇澳-南澳": ["蘇澳", "東澳", "蘇澳隧道", "東澳隧道", "東岳隧道"],
        "南澳-和平": ["南澳", "武塔", "漢本", "和平", "觀音隧道", "谷風隧道"],
        "和平-秀林": ["和平", "和仁", "崇德", "秀林", "和平隧道", "和中隧道", "和仁隧道", "中仁隧道", "仁水隧道", "大清水隧道", "錦文隧道", "匯德隧道", "崇德隧道", "清水斷崖", "下清水橋", "大清水"]
    }
    high_risk_keywords = ["封閉", "中斷", "坍方"]
    downgrade_keywords = ["改道", "替代道路", "行駛台9丁線", "單線雙向", "戒護通行", "放行"]
    mid_risk_keywords = ["落石", "施工", "管制", "事故", "壅塞", "車多", "濃霧", "作業"]
    
    results = {name: [] for name in sections.keys()}
    all_incidents = []
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        for page in pages_to_scrape:
            url = f"{base_url}{page}"
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            all_incidents.extend(soup.find_all('div', class_='w3-col l3 m6'))

        print(f"總共找到 {len(all_incidents)} 則路況事件容器。")

        for incident_container in all_incidents:
            desc_element = incident_container.find('td', text='描述')
            if not desc_element or not desc_element.find_next_sibling('td'): continue
            content = " ".join(desc_element.find_next_sibling('td').get_text().split())

            time_element = incident_container.find('td', text='時間')
            report_time = ""
            if time_element and time_element.find_next_sibling('td'):
                try:
                    report_time_str = time_element.find_next_sibling('td').get_text().strip()
                    # 【修改處】格式化為您要求的完整時間格式
                    report_time = f"通報時間: {datetime.strptime(report_time_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')}"
                except ValueError:
                    report_time = f"通報時間: {datetime.now(TAIPEI_TZ).strftime('%Y-%m-%d %H:%M')}"

            if any(keyword in content for keyword in ["台9線", "蘇花", "台9丁線"]):
                status = "事件"; css_class = "road-yellow"; is_high_risk = False
                
                for keyword in high_risk_keywords:
                    if keyword in content:
                        status = keyword; css_class = "road-red"; is_high_risk = True; break
                if not is_high_risk:
                    for keyword in mid_risk_keywords:
                        if keyword in content:
                            status = keyword; css_class = "road-yellow"; break
                
                if is_high_risk and any(keyword in content for keyword in downgrade_keywords):
                    status = f"管制 ({status}改道)"; css_class = "road-yellow"
                
                incident_assigned = False
                for section_name, keywords in sections.items():
                    if any(keyword in content for keyword in keywords):
                        # 【修改處】確保 section_name 也被加入到事件物件中
                        results[section_name].append({
                            "section": section_name,
                            "status": status,
                            "class": css_class,
                            "desc": f"（{content}）",
                            "time": report_time
                        })
                        incident_assigned = True
                
                if not incident_assigned:
                    print(f"未分類的蘇花路況: {content}")
                        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching road data: {e}")
        error_event = { "section": "全線", "status": "讀取失敗", "class": "road-red", "desc": "無法連接路況伺服器", "time": "" }
        for section_name in sections.keys():
            results[section_name].append(error_event)
            
    return results

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard FINAL POLISHED VERSION is running."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
