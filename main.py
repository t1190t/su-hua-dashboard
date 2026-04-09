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

# ==============================================================================
# 金鑰設定：建議在 Render 的「Environment Variables」中設定，不要寫在程式碼裡
# Render → 你的服務 → Environment → Add Environment Variable
#   TDX_APP_ID   = 你的TDX App ID
#   TDX_APP_KEY  = 你的TDX App Key
#   CWA_API_KEY  = CWA-B3D5458A-4530-4045-A702-27A786C1E934
# ==============================================================================
TDX_APP_ID  = os.environ.get('TDX_APP_ID',  't1190t-64266cda-41c7-451f')
TDX_APP_KEY = os.environ.get('TDX_APP_KEY', '0d5f5de8-ab0b-4d28-a573-92a3406c178c')
CWA_API_KEY = os.environ.get('CWA_API_KEY', 'CWA-B3D5458A-4530-4045-A702-27A786C1E934')

TAIPEI_TZ = pytz.timezone('Asia/Taipei')

# 快取設定（路況資料每 5 分鐘更新一次，避免超過 TDX 頻率限制）
cached_road_data = None
last_fetch_time  = 0
CACHE_DURATION_SECONDS = 300


# ─────────────────────────────────────────────
# 雨量分級
# ─────────────────────────────────────────────
def get_rain_level(value: float) -> tuple:
    if value < 0:    return "資料異常",   "rain-red",    "資料異常"
    if value > 200:  return "🟥 豪大雨",  "rain-red",    "豪大雨"
    if value > 130:  return "🟧 豪雨",    "rain-orange", "豪雨"
    if value > 80:   return "🟨 大雨",    "rain-yellow", "大雨"
    if value > 30:   return "🟦 中雨",    "rain-blue",   "中雨"
    if value > 0:    return "🟩 小雨",    "rain-green",  "小雨"
    return "⬜️ 無雨", "rain-none", "無雨"


# ─────────────────────────────────────────────
# 主儀表板 API
# ─────────────────────────────────────────────
@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    current_time = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    rain_info      = await get_cwa_rain_data()
    earthquake_info= await get_cwa_earthquake_data()
    typhoon_info   = await get_cwa_typhoon_data()
    road_info      = await get_suhua_road_data()
    return {
        "lastUpdate":    current_time,
        "rainInfo":      rain_info,
        "earthquakeInfo":earthquake_info,
        "roadInfo":      road_info,
        "typhoonInfo":   typhoon_info,
    }


# ─────────────────────────────────────────────
# 圖片代理（加上 Referer / User-Agent，否則氣象局會擋）
# ─────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Referer":    "https://www.cwa.gov.tw/",
}

@app.get("/api/radar-image")
async def get_radar_image():
    # 加上時間戳避免氣象局 CDN 回傳舊快取
    ts = int(time.time())
    image_url = f"https://www.cwa.gov.tw/Data/radar/CV1_3600.png?t={ts}"
    try:
        resp = requests.get(image_url, headers=BROWSER_HEADERS, timeout=12, verify=False)
        resp.raise_for_status()
        return Response(content=resp.content, media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    except Exception as e:
        print(f"[radar] 圖片讀取失敗: {e}")
        return Response(status_code=502)

@app.get("/api/rainfall-map")
async def get_rainfall_map():
    image_url = "https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/O-A0040-002?" \
                f"Authorization={CWA_API_KEY}&downloadType=WEB&format=png"
    try:
        resp = requests.get(image_url, headers=BROWSER_HEADERS, timeout=12, verify=False)
        resp.raise_for_status()
        ct = resp.headers.get("Content-Type", "image/png")
        return Response(content=resp.content, media_type=ct,
                        headers={"Cache-Control": "no-store"})
    except Exception as e:
        print(f"[rainfall-map] 圖片讀取失敗: {e}")
        # 備用來源
        try:
            backup = "https://c1.1968services.tw/map-data/O-A0040-002.jpg"
            resp2 = requests.get(backup, timeout=10, verify=False)
            resp2.raise_for_status()
            return Response(content=resp2.content, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except Exception:
            return Response(status_code=502)


# ─────────────────────────────────────────────
# 雨量資料（含未來 6 小時降雨預測）
# ─────────────────────────────────────────────
async def get_cwa_rain_forecast() -> Dict[str, str]:
    location_names = "蘇澳鎮,南澳鄉,秀林鄉,新城鄉"
    url = (f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-091"
           f"?Authorization={CWA_API_KEY}&locationName={location_names}&elementName=PoP6h")
    forecasts: Dict[str, str] = {}
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        locations = r.json().get("records", {}).get("location", [])
        for loc in locations:
            name = loc.get("locationName")
            pop6h = next((el for el in loc.get("weatherElement", [])
                          if el.get("elementName") == "PoP6h"), None)
            if pop6h and pop6h.get("time"):
                val = int(pop6h["time"][0]["parameter"]["parameterValue"])
                forecasts[name] = "無明顯降雨" if val <= 10 else f"{val}% 機率降雨"
            else:
                forecasts[name] = "預報資料異常"
    except Exception as e:
        print(f"[rain-forecast] {e}")
        for n in location_names.split(","):
            forecasts[n] = "預報讀取失敗"
    return forecasts

async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    station_ids = {
        "C0O920": "蘇澳鎮",
        "C0U9N0": "南澳鄉",
        "C0Z030": "秀林鄉",
        "C0T8A0": "新城鄉",
    }
    forecast_data = await get_cwa_rain_forecast()
    url = (f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
           f"?Authorization={CWA_API_KEY}&stationId={','.join(station_ids.keys())}")
    processed: List[Dict[str, Any]] = []
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        stations_data = {s["stationId"]: s
                         for s in r.json().get("records", {}).get("location", [])}
        for sid, sname in station_ids.items():
            s = stations_data.get(sid)
            if s:
                rain_str = next((item["elementValue"]
                                 for item in s["weatherElement"]
                                 if item["elementName"] == "HOUR_24"), "0")
                rain_val = float(rain_str)
                obs_time = (datetime.fromisoformat(s["time"]["obsTime"])
                            .astimezone(TAIPEI_TZ).strftime("%H:%M"))
                level_text, css_class, _ = get_rain_level(rain_val)
                processed.append({
                    "location": sname, "mm": rain_val, "class": css_class,
                    "level": level_text, "time": obs_time,
                    "forecast": forecast_data.get(sname, "N/A"),
                })
            else:
                processed.append({
                    "location": sname, "mm": "N/A", "class": "rain-nodata",
                    "level": "測站暫無回報", "time": "",
                    "forecast": forecast_data.get(sname, "N/A"),
                })
    except Exception as e:
        print(f"[rain] {e}")
        for sname in station_ids.values():
            processed.append({
                "location": sname, "mm": "N/A", "class": "rain-error",
                "level": "讀取失敗", "time": "", "forecast": "N/A",
            })
    return processed


# ─────────────────────────────────────────────
# 地震資料（宜蘭、花蓮、台東，72小時，≥2級）
# ─────────────────────────────────────────────
async def get_cwa_earthquake_data() -> List[Dict[str, Any]]:
    url = (f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/E-A0015-001"
           f"?Authorization={CWA_API_KEY}&limit=30")
    processed: List[Dict[str, Any]] = []
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        data = r.json()
        if not (data.get("records") and data["records"].get("Earthquake")):
            return processed

        three_days_ago = datetime.now(TAIPEI_TZ) - timedelta(days=3)

        for quake in data["records"]["Earthquake"]:
            eq_info = quake.get("EarthquakeInfo", {})
            quake_time_str = eq_info.get("OriginTime")
            if not quake_time_str:
                continue
            quake_time = datetime.fromisoformat(quake_time_str).astimezone(TAIPEI_TZ)
            if quake_time < three_days_ago:
                continue

            # 取三縣市震度
            levels = {"宜蘭縣": "0", "花蓮縣": "0", "台東縣": "0"}
            for area in quake.get("Intensity", {}).get("ShakingArea", []):
                desc = area.get("AreaDesc", "")
                if desc in levels:
                    levels[desc] = area.get("AreaIntensity", "0")

            def to_int(s: str) -> int:
                try:
                    return int(s.replace("級", ""))
                except ValueError:
                    return 0

            yilan_int   = to_int(levels["宜蘭縣"])
            hualien_int = to_int(levels["花蓮縣"])
            taitung_int = to_int(levels["台東縣"])

            # 只顯示有感（任一縣市 ≥ 2 級）
            if max(yilan_int, hualien_int, taitung_int) < 2:
                continue

            epicenter   = eq_info.get("Epicenter", {})
            mag_value   = eq_info.get("Magnitude", {}).get("MagnitudeValue", 0)
            focal_depth = eq_info.get("FocalDepth", 0)
            report_url  = quake.get("Web", "")

            processed.append({
                "time":          quake_time.strftime("%Y-%m-%d %H:%M"),
                "location":      epicenter.get("Location", "不明"),
                "magnitude":     mag_value,
                "depth":         focal_depth,
                "hualien_level": str(hualien_int),
                "yilan_level":   str(yilan_int),
                "taitung_level": str(taitung_int),
                "report_url":    report_url,
            })

    except Exception as e:
        print(f"[earthquake] {e}")
    return processed


# ─────────────────────────────────────────────
# 颱風資料
# ─────────────────────────────────────────────
async def get_cwa_typhoon_data() -> Optional[Dict[str, Any]]:
    url = (f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/T-A0001-001"
           f"?Authorization={CWA_API_KEY}")
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        data = r.json()
        warnings = (data.get("records", {})
                    .get("sea_typhoon_warning", {})
                    .get("typhoon_warning_summary", {})
                    .get("SeaTyphoonWarning"))
        if warnings:
            t = warnings[0]
            update_time = (datetime.fromisoformat(t["issue_time"])
                           .astimezone(TAIPEI_TZ).strftime("%m-%d %H:%M"))
            return {
                "name":         t["typhoon_name"],
                "warning_type": t["warning_type"],
                "update_time":  update_time,
                "location":     t["center_location"],
                "wind_speed":   t["max_wind_speed"],
                "status":       t["warning_summary"]["content"],
                "img_url":      "https://www.cwa.gov.tw/Data/typhoon/TY_NEWS/TY_NEWS_0.jpg",
            }
    except Exception as e:
        status_code = getattr(getattr(e, 'response', None), 'status_code', None)
        if status_code != 404:
            print(f"[typhoon] {e}")
    return None


# ─────────────────────────────────────────────
# 蘇花公路路況（TDX 公路局 API）
# ─────────────────────────────────────────────
def get_tdx_access_token() -> Optional[str]:
    auth_url = ("https://tdx.transportdata.tw/auth/realms/TDXConnect"
                "/protocol/openid-connect/token")
    try:
        r = requests.post(
            auth_url,
            data={"grant_type": "client_credentials",
                  "client_id": TDX_APP_ID,
                  "client_secret": TDX_APP_KEY},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        r.raise_for_status()
        print("✅ TDX token 取得成功")
        return r.json().get("access_token")
    except Exception as e:
        print(f"❌ TDX token 取得失敗: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   回應內容: {e.response.text}")
        return None

async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    global cached_road_data, last_fetch_time

    if cached_road_data and (time.time() - last_fetch_time < CACHE_DURATION_SECONDS):
        print("🔄 從快取讀取路況")
        return cached_road_data

    print("🚀 向 TDX 取得最新路況...")

    # 路段關鍵字定義（地名 → 路段）
    sections: Dict[str, List[str]] = {
        "蘇澳－南澳": ["蘇澳", "東澳", "蘇澳隧道", "東澳隧道", "東岳隧道"],
        "南澳－和平": ["南澳", "武塔", "漢本", "和平", "觀音隧道", "谷風隧道"],
        "和平－秀林": ["和平", "和仁", "崇德", "秀林", "中仁隧道", "和平隧道",
                    "和中隧道", "和中橋", "仁水隧道", "大清水隧道",
                    "錦文隧道", "匯德隧道", "崇德隧道", "清水斷崖",
                    "下清水橋", "大清水"],
    }
    high_risk_kw   = ["封閉", "中斷", "坍方"]
    downgrade_kw   = ["改道", "替代道路", "行駛台9丁線", "單線雙向", "戒護通行", "放行"]
    mid_risk_kw    = ["落石", "施工", "管制", "事故", "壅塞", "車多", "濃霧", "作業"]
    partial_kw     = ["單線", "單側", "車道", "非全路幅", "慢車道", "機動"]
    new_suhua_lmk  = ["蘇澳隧道", "東澳隧道", "觀音隧道", "谷風隧道",
                     "中仁隧道", "仁水隧道"]
    new_suhua_km   = [(104, 113), (124, 145), (148, 160)]

    results: Dict[str, List] = {name: [] for name in sections}

    token = get_tdx_access_token()
    if not token:
        err = {"section": "全線", "status": "認證失敗", "class": "road-red",
               "desc": "無法取得 TDX 授權，請確認金鑰是否有效", "time": "",
               "is_old_road": False, "detail_url": ""}
        for name in sections:
            results[name].append(err)
        return results

    api_url = ("https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Live/News/Highway"
               "?$orderby=PublishTime desc&$top=150&$format=JSON")
    try:
        r = requests.get(api_url,
                         headers={"Authorization": f"Bearer {token}"},
                         timeout=15)
        r.raise_for_status()
        news_items = r.json().get("Newses", [])
        print(f"✅ TDX 取得 {len(news_items)} 則公路消息")

        suhua_news = [
            n for n in news_items
            if "台9" in (n.get("Title","") + n.get("Description","")) or
               "蘇花" in (n.get("Title","") + n.get("Description",""))
        ]
        print(f"🔍 蘇花相關消息 {len(suhua_news)} 則")

        for news in suhua_news:
            title   = news.get("Title", "")
            desc    = news.get("Description", "")
            content = f"{title}：{desc}"
            if not desc:
                continue

            # 時間格式化
            try:
                upd = (datetime.fromisoformat(news.get("UpdateTime","").replace("Z","+00:00"))
                       .astimezone(TAIPEI_TZ))
                pub = (datetime.fromisoformat(news.get("PublishTime","").replace("Z","+00:00"))
                       .astimezone(TAIPEI_TZ))
                time_str = f"更新：{upd.strftime('%m-%d %H:%M')}（首發：{pub.strftime('%m-%d %H:%M')}）"
            except (ValueError, TypeError):
                time_str = ""

            # 狀態分類
            status    = "事件"
            css_class = "road-yellow"
            is_high   = False
            for kw in high_risk_kw:
                if kw in content:
                    status = kw; css_class = "road-red"; is_high = True; break
            if not is_high:
                for kw in mid_risk_kw:
                    if kw in content:
                        status = kw; break

            if is_high:
                if any(k in content for k in partial_kw):
                    status = f"管制（{status}單線）"; css_class = "road-yellow"
                elif any(k in content for k in downgrade_kw):
                    status = f"管制（{status}改道）"; css_class = "road-yellow"

            # 判斷新/舊蘇花
            is_old = False
            if any(lmk in content for lmk in new_suhua_lmk):
                is_old = False
            else:
                km_m = re.search(r'(\d+\.?\d*)[Kk]', content)
                if km_m:
                    try:
                        km = float(km_m.group(1))
                        is_old = not any(lo <= km <= hi for lo, hi in new_suhua_km)
                    except ValueError:
                        is_old = "台9丁" in content
                else:
                    is_old = "台9丁" in content

            # 分配路段
            classified = False
            for sname, keywords in sections.items():
                if any(kw in content for kw in keywords):
                    results[sname].append({
                        "section":    sname,
                        "status":     status,
                        "class":      css_class,
                        "desc":       f"【{title}】{desc}",
                        "time":       time_str,
                        "is_old_road":is_old,
                        "detail_url": news.get("NewsURL", ""),
                    })
                    classified = True
                    break

            if not classified:
                results.setdefault("其他蘇花路段", []).append({
                    "section":    "其他蘇花路段",
                    "status":     status,
                    "class":      css_class,
                    "desc":       f"【{title}】{desc}",
                    "time":       time_str,
                    "is_old_road":is_old,
                    "detail_url": news.get("NewsURL", ""),
                })

        cached_road_data = results
        last_fetch_time  = time.time()
        print("✅ 路況快取已更新")

    except Exception as e:
        print(f"❌ TDX 路況讀取失敗: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   回應: {e.response.text}")
        err = {"section": "全線", "status": "讀取失敗", "class": "road-red",
               "desc": "無法連線到 TDX 伺服器", "time": "",
               "is_old_road": False, "detail_url": ""}
        for name in sections:
            results[name].append(err)

    return results


# ─────────────────────────────────────────────
# 根路由
# ─────────────────────────────────────────────
@app.get("/")
def read_root():
    return {"status": "Guardian Angel Dashboard is running ✅"}

@app.head("/")
def read_root_head():
    return Response(status_code=200)
