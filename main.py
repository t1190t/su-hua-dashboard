import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz
import re
import json # 引入 json 模組來處理可能的錯誤

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

CWA_API_KEY = os.environ.get('CWA_API_KEY', 'CWA-B3D5458A-4530-4045-A702-27A786C1E934') # 方便測試，直接填入您的KEY
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

# --- 資料獲取函式 (其他部分保持不變) ---
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
        if e.response and e.response.status_code == 404:
            pass
        else:
            print(f"Error fetching typhoon data: {e}")
    return None

# ==============================================================================
# ===== ✨底下是路況函式的最終修正版，加入了更完整的標頭 (Headers) ✨ =====
# ==============================================================================
async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    api_url = "https://www.1968services.tw/api/getIncidents"
    
    # 【本次修正重點】加入更完整的標頭，特別是 `Referer`
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json;charset=UTF-8',
        'Origin': 'https://www.1968services.tw',
        'Referer': 'https://www.1968services.tw/pbs-incident?region=e', # 告訴伺服器我們是從這個頁面來的
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    sections = {
        "蘇澳-南澳": ["蘇澳", "東澳", "蘇澳隧道", "東澳隧道", "東岳隧道"],
        "南澳-和平": ["南澳", "武塔", "漢本", "和平", "觀音隧道", "谷風隧道"],
        "和平-秀林": ["和平", "和仁", "崇德", "秀林", "和平隧道", "和中隧道", "和仁隧道", "中仁隧道", "仁水隧道", "大清水隧道", "錦文隧道", "匯德隧道", "崇德隧道", "清水斷崖", "下清水橋", "大清水"]
    }
    high_risk_keywords = ["封閉", "中斷", "坍方"]
    downgrade_keywords = ["改道", "替代道路", "行駛台9丁線", "單線雙向", "戒護通行", "放行"]
    mid_risk_keywords = ["落石", "施工", "管制", "事故", "壅塞", "車多", "濃霧", "作業"]
    degree_keywords = ["單線", "單側", "車道", "非全路幅", "慢車道", "機動"]
    
    results = {name: [] for name in sections.keys()}
    response = None # 先宣告 response 變數
    
    try:
        response = requests.post(api_url, json={"region": "e"}, headers=headers, timeout=15)
        response.raise_for_status()
        
        incidents = response.json()
        
        print(f"✅ 成功透過 API 取得 {len(incidents)} 則路況事件。")

        for incident in incidents:
            content = incident.get("dsc", "")
            report_time_str = incident.get("time", "")
            
            report_time = ""
            if report_time_str:
                try:
                    report_time = f"通報時間: {datetime.strptime(report_time_str, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')}"
                except ValueError:
                    report_time = f"通報時間: {datetime.now(TAIPEI_TZ).strftime('%Y-%m-%d %H:%M')}"
            
            detail_url = ""
            incident_id = incident.get("id")
            if incident_id:
                detail_url = f"https://www.1968services.tw/incident/{incident_id}"

            if any(keyword in content for keyword in ["台9線", "蘇花", "台9丁線"]):
                status = "事件"; css_class = "road-yellow"; is_high_risk = False
                
                for keyword in high_risk_keywords:
                    if keyword in content:
                        status = keyword; css_class = "road-red"; is_high_risk = True; break
                if not is_high_risk:
                    for keyword in mid_risk_keywords:
                        if keyword in content:
                            status = keyword; css_class = "road-yellow"; break
                
                is_partial_closure = any(keyword in content for keyword in degree_keywords)
                has_downgrade_option = any(keyword in content for keyword in downgrade_keywords)
                if is_high_risk:
                    if is_partial_closure:
                        status = f"管制 ({status}單線)"; css_class = "road-yellow"
                    elif has_downgrade_option:
                        status = f"管制 ({status}改道)"; css_class = "road-yellow"

                is_old_road_event = "台9丁線" in content
                
                new_suhua_tunnels = ["蘇澳隧道", "東澳隧道", "觀音隧道", "谷風隧道", "中仁隧道", "仁水隧道"]
                is_new_road_event = any(tunnel in content for tunnel in new_suhua_tunnels)
                
                if is_new_road_event:
                    is_old_road_event = False
                elif not is_old_road_event:
                    km_match = re.search(r'(\d+\.?\d*)[Kk]', content)
                    if km_match:
                        try:
                            km = float(km_match.group(1))
                            new_ranges = [(104, 113), (124, 145), (148, 160)]
                            if not any(start <= km <= end for start, end in new_ranges):
                                is_old_road_event = True
                        except ValueError:
                            pass
                
                for section_name, keywords in sections.items():
                    if any(keyword in content for keyword in keywords):
                        results[section_name].append({
                            "section": section_name, "status": status, "class": css_class,
                            "desc": f"（{content}）", "time": report_time, "is_old_road": is_old_road_event,
                            "detail_url": detail_url
                        })
                        
    except json.JSONDecodeError as e:
        print(f"❌ 解析 JSON 失敗: {e}")
        # 【本次修正重點】如果解析JSON失敗，印出伺服器回傳的原始文字內容
        if response:
             print(f"收到的伺服器回應內容並非JSON格式:\n--- START ---\n{response.text}\n--- END ---")
        for section_name in sections.keys():
            results[section_name].append({ "section": "全線", "status": "解析失敗", "class": "road-red", "desc": "伺服器回應格式錯誤", "time": "", "is_old_road": False, "detail_url": "" })

    except requests.exceptions.RequestException as e:
        print(f"❌ 網路請求失敗: {e}")
        for section_name in sections.keys():
            results[section_name].append({ "section": "全線", "status": "讀取失敗", "class": "road-red", "desc": "無法連接路況伺服器", "time": "", "is_old_road": False, "detail_url": "" })
            
    return results

@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard FINAL VERSION is running."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
