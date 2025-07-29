import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz
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

# ==============================================================================
# ===== ✨ 請再次確認您已填入正確的 TDX 金鑰 (並用雙引號包起來) ✨ =====
# ==============================================================================
TDX_APP_ID = "t1190t-cb75f4a4-e514-489f"  # 請替換成您的 APP ID
TDX_APP_KEY = "dc00bc01-dff4-47cb-97f4-88fec81e69cc" # 請替換成您的 APP KEY
# ==============================================================================

CWA_API_KEY = os.environ.get('CWA_API_KEY', 'CWA-B3D5458A-4530-4045-A702-27A786C1E934')
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# --- Helper Functions (保持不變) ---
def get_rain_level(value: float) -> tuple[str, str, str]:
    if value < 0: return "資料異常", "rain-red", "資料異常"
    if value > 200: return "🟥 豪大雨", "rain-red", "豪大雨"
    if value > 130: return "🟧 豪雨", "rain-orange", "豪雨"
    if value > 80: return "🟨 大雨", "rain-yellow", "大雨"
    if value > 30: return "🟦 中雨", "rain-blue", "中雨"
    if value > 0: return "🟩 小雨", "rain-green", "小雨"
    return "⬜️ 無雨", "rain-none", "無雨"

# --- API 路由定義 (保持不變) ---
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

# --- 其他資料獲取函式 (為求簡潔省略，保持不變) ---
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
        
async def get_cwa_rain_forecast():
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

async def get_cwa_rain_data():
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

async def get_cwa_earthquake_data():
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

async def get_cwa_typhoon_data():
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
# ===== ✨ TDX API 函式 (最終權威版，參照官方文件) ✨ =====
# ==============================================================================
def get_tdx_access_token():
    """
    步驟1: 獲取 TDX 的 Access Token
    """
    auth_url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    body = {
        "grant_type": "client_credentials",
        "client_id": TDX_APP_ID,
        "client_secret": TDX_APP_KEY,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        response = requests.post(auth_url, data=body, headers=headers)
        response.raise_for_status()
        token_data = response.json()
        print("✅ 成功獲取 TDX Access Token！")
        return token_data.get("access_token")
    except requests.exceptions.RequestException as e:
        print(f"❌ 獲取 TDX Access Token 失敗: {e}")
        if e.response:
            print(f"    伺服器回應錯誤: {e.response.text}")
        return None

async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    """
    步驟2: 使用 Access Token 獲取蘇花公路路況，並進行分類
    """
    sections = {
        "蘇澳-南澳": ["蘇澳", "東澳", "蘇澳隧道", "東澳隧道", "東岳隧道"],
        "南澳-和平": ["南澳", "武塔", "漢本", "和平", "觀音隧道", "谷風隧道"],
        "和平-秀林": ["和平", "和仁", "崇德", "秀林", "和平隧道", "和中隧道", "和中橋", "仁水隧道", "大清水隧道", "錦文隧道", "匯德隧道", "崇德隧道", "清水斷崖", "下清水橋", "大清水"]
    }
    high_risk_keywords = ["封閉", "中斷", "坍方"]
    downgrade_keywords = ["改道", "替代道路", "行駛台9丁線", "單線雙向", "戒護通行", "放行"]
    mid_risk_keywords = ["落石", "施工", "管制", "事故", "壅塞", "車多", "濃霧", "作業"]
    degree_keywords = ["單線", "單側", "車道", "非全路幅", "慢車道", "機動"]
    
    results = {name: [] for name in sections.keys()}
    
    access_token = get_tdx_access_token()
    
    if not access_token:
        error_event = { "section": "全線", "status": "認證失敗", "class": "road-red", "desc": "無法獲取TDX授權", "time": "", "is_old_road": False, "detail_url": "" }
        for section_name in sections.keys():
            results[section_name].append(error_event)
        return results

    # 【本次修正重點】使用您找到的、最正確的「公路消息 v2 API」路徑
    road_event_url = "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/News/Road/Provincial?$filter=contains(RoadName,'台9')&$orderby=PublishTime desc&$top=50&$format=JSON"
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.get(road_event_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        news_items = data.get("Newses", []) # 根據 Swagger，v2 的資料在 "Newses" 欄位中
        
        print(f"✅ 成功從 TDX API 獲取 {len(news_items)} 則路況消息。")

        for news in news_items:
            content = news.get("Description", "") # 描述欄位是 Description
            if not content:
                continue

            report_time = ""
            update_time_str = news.get("PublishTime") # 使用發布時間
            if update_time_str:
                try:
                    utc_time = datetime.fromisoformat(update_time_str.replace('Z', '+00:00'))
                    taipei_time = utc_time.astimezone(TAIPEI_TZ)
                    report_time = f"發布時間: {taipei_time.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, TypeError):
                    pass

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

            road_name = news.get("RoadName")
            is_old_road_event = (road_name == '台9丁線') or ("台9丁線" in content)
            
            classified = False
            for section_name, keywords in sections.items():
                if any(keyword in content for keyword in keywords):
                    results[section_name].append({
                        "section": section_name, "status": status, "class": css_class,
                        "desc": f"（{content}）", "time": report_time, "is_old_road": is_old_road_event,
                        "detail_url": news.get("NewsURL", "") # 可以加上消息的原始網址
                    })
                    classified = True
                    break
            
            if not classified:
                print(f"    [未分類消息]: {content}")


    except requests.exceptions.RequestException as e:
        print(f"❌ 獲取 TDX 路況資料失敗: {e}")
        if e.response:
            print(f"    伺服器回應錯誤: {e.response.text}")
        error_event = { "section": "全線", "status": "讀取失敗", "class": "road-red", "desc": "無法連接TDX路況伺服器", "time": "", "is_old_road": False, "detail_url": "" }
        for section_name in sections.keys():
            results[section_name].append(error_event)
            
    return results

# --- FastAPI 根路由 (保持不變) ---
@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard FINAL VERSION is running."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
