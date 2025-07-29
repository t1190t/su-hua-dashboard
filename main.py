import os
import requests
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import warnings
import pytz
import re
import time # 引入時間模組，用於快取

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
TDX_APP_ID = "t1190t-d57e05ff-dc8c-4bc1"  # 請替換成您的 APP ID
TDX_APP_KEY = "68276435-02a9-401d-8a09-636739b38cf7" # 請替換成您的 APP KEY
# ==============================================================================

CWA_API_KEY = os.environ.get('CWA_API_KEY', 'CWA-B3D5458A-4530-4045-A702-27A786C1E934')
TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# ==============================================================================
# ===== ✨ 全域變數，用於儲存快取的資料 ✨ =====
# ==============================================================================
cached_road_data = None
last_fetch_time = 0
CACHE_DURATION_SECONDS = 300  # 快取持續時間 (300秒 = 5分鐘)
# ==============================================================================


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
# ... (此處省略其他 CWA, radar, map 等函式，它們維持不變) ...

# ==============================================================================
# ===== ✨ TDX API 函式 (最終版，使用正確 API 路徑) ✨ =====
# ==============================================================================
def get_tdx_access_token():
    """步驟1: 獲取 TDX 的 Access Token"""
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

async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    """步驟2: 使用 Access Token 獲取蘇花公路路況，並進行分類 (含快取)"""
    global cached_road_data, last_fetch_time

    current_time = time.time()
    if cached_road_data and (current_time - last_fetch_time < CACHE_DURATION_SECONDS):
        print("🔄 從快取中讀取路況資料...")
        return cached_road_data

    print("🚀 快取過期或不存在，重新從 TDX API 獲取資料...")
    
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
        for section_name in sections.keys(): results[section_name].append(error_event)
        return results

    # 【本次修正重點】使用您找到的、最終正確的「即時事件 v1 API」路徑
    road_event_url = "https://tdx.transportdata.tw/api/basic/v1/Traffic/RoadEvent/LiveEvent/Highway?$filter=contains(Road,'台9')&$orderby=UpdateTime desc&$top=50&$format=JSON"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        response = requests.get(road_event_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        live_events = data.get("LiveEvents", [])
        
        print(f"✅ 成功從 TDX API 獲取 {len(live_events)} 則路況事件。")

        for event in live_events:
            content = event.get("Description", "")
            if not content: continue

            report_time = ""
            update_time_str = event.get("UpdateTime")
            if update_time_str:
                try:
                    # TDX v1 的時間格式可能帶有 "+08:00"，可以直接解析
                    dt_object = datetime.fromisoformat(update_time_str)
                    report_time = f"更新時間: {dt_object.astimezone(TAIPEI_TZ).strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, TypeError): pass

            status = "事件"; css_class = "road-yellow"; is_high_risk = False
            for keyword in high_risk_keywords:
                if keyword in content: status = keyword; css_class = "road-red"; is_high_risk = True; break
            if not is_high_risk:
                for keyword in mid_risk_keywords:
                    if keyword in content: status = keyword; css_class = "road-yellow"; break
            
            is_partial_closure = any(keyword in content for keyword in degree_keywords)
            has_downgrade_option = any(keyword in content for keyword in downgrade_keywords)
            if is_high_risk:
                if is_partial_closure: status = f"管制 ({status}單線)"; css_class = "road-yellow"
                elif has_downgrade_option: status = f"管制 ({status}改道)"; css_class = "road-yellow"

            # 從 Location 物件中取得路名
            road_name = event.get("Location", {}).get("FreeExpressHighway", {}).get("Road", "")
            is_old_road_event = (road_name == '台9丁') or ("台9丁線" in content)
            
            classified = False
            for section_name, keywords in sections.items():
                if any(keyword in content for keyword in keywords):
                    results[section_name].append({
                        "section": section_name, "status": status, "class": css_class,
                        "desc": f"（{content}）", "time": report_time, "is_old_road": is_old_road_event,
                        "detail_url": "" 
                    })
                    classified = True
                    break
            
            if not classified: print(f"    [未分類事件]: {content}")
        
        cached_road_data = results
        last_fetch_time = time.time()
        print("🔄 路況資料已更新至快取。")

    except requests.exceptions.RequestException as e:
        print(f"❌ 獲取 TDX 路況資料失敗: {e}")
        if e.response: print(f"    伺服器回應錯誤: {e.response.text}")
        error_event = { "section": "全線", "status": "讀取失敗", "class": "road-red", "desc": "無法連接TDX伺服器", "time": "", "is_old_road": False, "detail_url": "" }
        for section_name in sections.keys(): results[section_name].append(error_event)
            
    return results

# --- FastAPI 根路由 (保持不變) ---
@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard FINAL VERSION is running."}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
