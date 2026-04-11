import os
import json
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

import gspread
from google.oauth2.service_account import Credentials

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TDX_APP_ID     = os.environ.get('TDX_APP_ID',  't1190t-64266cda-41c7-451f')
TDX_APP_KEY    = os.environ.get('TDX_APP_KEY', '0d5f5de8-ab0b-4d28-a573-92a3406c178c')
CWA_API_KEY    = os.environ.get('CWA_API_KEY', 'CWA-B3D5458A-4530-4045-A702-27A786C1E934')
GOOGLE_SA_JSON = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '')
SHEET_ID       = '1oG1ydRWD7eELqB2myuoECuQFTffkCGqirwROLe3SXcE'

TAIPEI_TZ = pytz.timezone('Asia/Taipei')

cached_road_data     = None
last_fetch_time      = 0
CACHE_DURATION_SECONDS = 300

cached_hospital_data = None
hospital_cache_time  = 0
HOSPITAL_CACHE_SECONDS = 30 * 60


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
# 醫院資料（Google Sheets）
# ─────────────────────────────────────────────
def _parse_dt(val: str) -> Optional[datetime]:
    if not val or not val.strip():
        return None
    val = val.strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M",
        "%Y-%m-%d", "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def _format_date(val: str) -> str:
    dt = _parse_dt(val)
    if dt:
        return dt.strftime("%Y-%m-%d")
    return val.strip()


@app.get("/api/hospital-data")
async def get_hospital_data():
    global cached_hospital_data, hospital_cache_time

    if cached_hospital_data and (time.time() - hospital_cache_time < HOSPITAL_CACHE_SECONDS):
        return cached_hospital_data

    if not GOOGLE_SA_JSON:
        return {"error": "GOOGLE_SERVICE_ACCOUNT_JSON 未設定", "DB": {}, "TIME_DB": {}, "stats": {}}

    try:
        creds_dict = json.loads(GOOGLE_SA_JSON)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
    except Exception as e:
        print(f"[hospital] Sheets 授權失敗: {e}")
        return {"error": str(e), "DB": {}, "TIME_DB": {}, "stats": {}}

    outbound_rows = []
    transfer_rows = []
    
    # 分別讀取兩個工作表
    try:
        ws_out = sh.worksheet("外接出勤")
        outbound_rows = ws_out.get_all_values()
    except Exception as e:
        print(f"[hospital] 外接出勤讀取失敗: {e}")

    try:
        ws_trans = sh.worksheet("轉出")
        transfer_rows = ws_trans.get_all_values()
    except Exception as e:
        print(f"[hospital] 轉出讀取失敗: {e}")

    DB: Dict[str, Any] = {}
    time_records: Dict[str, list] = {}
    outbound_count = 0
    transfer_count = 0

    # 共用的資料處理函數
    def process_data(rows, hosp_col_name, mission_type):
        nonlocal outbound_count, transfer_count
        if len(rows) < 2:
            return
        headers = rows[0]
        col = {h.strip(): i for i, h in enumerate(headers)}

        def get_cell(row, name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        for row in rows[1:]:
            name = get_cell(row, hosp_col_name)
            if not name:
                continue

            if mission_type == "outbound":
                outbound_count += 1
            else:
                transfer_count += 1

            date_fmt = _format_date(get_cell(row, "出勤日期"))
            county   = get_cell(row, "出勤縣市")
            unit     = get_cell(row, "轉出單位")
            # 嘗試抓取電話，不同表單欄位名稱可能不同，容錯處理
            phone    = get_cell(row, "轉出醫院之電話") or get_cell(row, "轉回醫院之電話") or ""
            contact  = get_cell(row, "對方聯絡人") or ""

            if name not in DB:
                DB[name] = {"count": 0, "county": county, "records": []}

            DB[name]["count"] += 1
            if county:
                DB[name]["county"] = county
            DB[name]["records"].append({
                "date": date_fmt, "phone": phone,
                "contact": contact, "unit": unit, "county": county,
                "type": mission_type
            })

            # 針對外接出勤計算時間統計
            if mission_type == "outbound":
                t_depart = _parse_dt(get_cell(row, "出發時間"))
                t_arrive = _parse_dt(get_cell(row, "抵達他院時間"))
                t_return = _parse_dt(get_cell(row, "回程時間"))

                if t_depart and t_arrive and t_return:
                    go_mins   = (t_arrive - t_depart).total_seconds() / 60
                    stay_mins = (t_return - t_arrive).total_seconds() / 60
                    if 0 < go_mins < 600 and 0 < stay_mins < 600:
                        if name not in time_records:
                            time_records[name] = []
                        time_records[name].append({"go": go_mins, "stay": stay_mins, "date": date_fmt})

    # 執行資料處理 (注意：第二個參數為表單中的醫院欄位名稱)
    process_data(outbound_rows, "轉出院所名稱", "outbound")
    process_data(transfer_rows, "轉回院所名稱", "transfer")

    # 按日期降序排列
    for name in DB:
        DB[name]["records"].sort(key=lambda r: r["date"], reverse=True)

    # 建立 TIME_DB
    TIME_DB: Dict[str, Any] = {}
    for name, entries in time_records.items():
        if not entries: continue
        go_list   = [e["go"]   for e in entries]
        stay_list = [e["stay"] for e in entries]
        max_entry = max(entries, key=lambda e: e["stay"])
        TIME_DB[name] = {
            "avg_go":        round(sum(go_list)   / len(go_list)),
            "avg_stay":      round(sum(stay_list) / len(stay_list)),
            "max_stay":      round(max_entry["stay"]),
            "max_stay_date": max_entry["date"],
        }

    total_missions  = outbound_count + transfer_count
    total_hospitals = len(DB)
    counties        = {v["county"] for v in DB.values() if v["county"]}

    # 防呆機制：只採計 2019 到 2030 年的資料，避免人為輸入錯字導致年份暴增
    valid_years = {r["date"][:4] for v in DB.values() for r in v["records"] if "2019" <= r["date"][:4] <= "2030"}
    years_span = max(1, len(valid_years))

    result = {
        "DB": DB,
        "TIME_DB": TIME_DB,
        "stats": {
            "total_missions":  total_missions,
            "outbound_missions": outbound_count,
            "transfer_missions": transfer_count,
            "total_hospitals": total_hospitals,
            "total_counties":  len(counties),
            "years_span":      years_span,
        },
    }

    cached_hospital_data = result
    hospital_cache_time  = time.time()
    print(f"[hospital] ✅ 快取已更新：總共 {total_missions} 筆 (外接 {outbound_count}, 轉出 {transfer_count})，{total_hospitals} 家")
    return result


# ─────────────────────────────────────────────
# 主儀表板 API
# ─────────────────────────────────────────────
@app.get("/api/dashboard-data")
async def get_dashboard_data() -> Dict[str, Any]:
    current_time    = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")
    rain_info       = await get_cwa_rain_data()
    earthquake_info = await get_cwa_earthquake_data()
    typhoon_info    = await get_cwa_typhoon_data()
    road_info       = await get_suhua_road_data()
    return {
        "lastUpdate":     current_time,
        "rainInfo":       rain_info,
        "earthquakeInfo": earthquake_info,
        "roadInfo":       road_info,
        "typhoonInfo":    typhoon_info,
    }


# ─────────────────────────────────────────────
# 圖片代理
# ─────────────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Referer":    "https://www.cwa.gov.tw/",
}

@app.get("/api/radar-image")
async def get_radar_image():
    ts = int(time.time())
    try:
        resp = requests.get(f"https://www.cwa.gov.tw/Data/radar/CV1_3600.png?t={ts}",
                            headers=BROWSER_HEADERS, timeout=12, verify=False)
        resp.raise_for_status()
        return Response(content=resp.content, media_type="image/png",
                        headers={"Cache-Control": "no-store"})
    except Exception as e:
        print(f"[radar] {e}")
        return Response(status_code=502)

@app.get("/api/rainfall-map")
async def get_rainfall_map():
    url = (f"https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/O-A0040-002?"
           f"Authorization={CWA_API_KEY}&downloadType=WEB&format=png")
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=12, verify=False)
        resp.raise_for_status()
        return Response(content=resp.content, media_type=resp.headers.get("Content-Type", "image/png"),
                        headers={"Cache-Control": "no-store"})
    except Exception as e:
        print(f"[rainfall-map] {e}")
        try:
            resp2 = requests.get("https://c1.1968services.tw/map-data/O-A0040-002.jpg", timeout=10, verify=False)
            resp2.raise_for_status()
            return Response(content=resp2.content, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        except Exception:
            return Response(status_code=502)


# ─────────────────────────────────────────────
# 雨量資料
# ─────────────────────────────────────────────
async def get_cwa_rain_forecast() -> Dict[str, str]:
    county_to_labels = {"宜蘭縣": ["蘇澳鎮", "南澳鄉"], "花蓮縣": ["秀林鄉", "新城鄉"]}
    url = (f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-C0032-001"
           f"?Authorization={CWA_API_KEY}&locationName=宜蘭縣,花蓮縣")
    forecasts: Dict[str, str] = {}
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        for loc in r.json().get("records", {}).get("location", []):
            county = loc.get("locationName", "")
            labels = county_to_labels.get(county, [])
            if not labels:
                continue
            pop_el = next((el for el in loc.get("weatherElement", [])
                           if el.get("elementName") == "PoP"), None)
            if pop_el and pop_el.get("time"):
                val_str = pop_el["time"][0]["parameter"]["parameterName"]
                try:
                    val = int(val_str)
                    text = "無明顯降雨" if val <= 10 else f"{val}% 機率降雨"
                except ValueError:
                    text = val_str
                for label in labels:
                    forecasts[label] = text
    except Exception as e:
        print(f"[rain-forecast] {e}")
    return forecasts


async def get_cwa_rain_data() -> List[Dict[str, Any]]:
    targets = [
        ("宜蘭縣", "蘇澳鎮", "蘇澳鎮"), ("宜蘭縣", "南澳鄉", "南澳鄉"),
        ("花蓮縣", "秀林鄉", "秀林鄉"), ("花蓮縣", "新城鄉", "新城鄉"),
    ]
    target_map    = {(c, t): label for c, t, label in targets}
    display_order = [label for _, _, label in targets]
    forecast_data = await get_cwa_rain_forecast()
    found: Dict[str, Any] = {}

    try:
        r = requests.get(
            f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
            f"?Authorization={CWA_API_KEY}&limit=2000",
            verify=False, timeout=20)
        r.raise_for_status()
        for s in r.json().get("records", {}).get("Station", []):
            geo   = s.get("GeoInfo", {})
            label = target_map.get((geo.get("CountyName", ""), geo.get("TownName", "")))
            if label and label not in found:
                try:
                    rain_val = float(s.get("RainfallElement", {}).get("Past24hr", {}).get("Precipitation", "-1"))
                except ValueError:
                    rain_val = -1.0
                try:
                    obs_time = (datetime.fromisoformat(s.get("ObsTime", {}).get("DateTime", ""))
                                .astimezone(TAIPEI_TZ).strftime("%H:%M"))
                except Exception:
                    obs_time = ""
                level_text, css_class, _ = get_rain_level(rain_val)
                found[label] = {
                    "location": label, "mm": rain_val, "class": css_class,
                    "level": level_text, "time": obs_time,
                    "forecast": forecast_data.get(label, "N/A"),
                }
    except Exception as e:
        print(f"[rain] {e}")

    processed = []
    for label in display_order:
        processed.append(found[label] if label in found else {
            "location": label, "mm": "N/A", "class": "rain-nodata",
            "level": "測站暫無回報", "time": "",
            "forecast": forecast_data.get(label, "N/A"),
        })
    return processed


# ─────────────────────────────────────────────
# 地震資料
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
            levels = {"宜蘭縣": "0", "花蓮縣": "0", "台東縣": "0"}
            for area in quake.get("Intensity", {}).get("ShakingArea", []):
                desc = area.get("AreaDesc", "")
                if desc in levels:
                    levels[desc] = area.get("AreaIntensity", "0")
            def to_int(s):
                try: return int(s.replace("級", ""))
                except: return 0
            yi, hu, ta = to_int(levels["宜蘭縣"]), to_int(levels["花蓮縣"]), to_int(levels["台東縣"])
            if max(yi, hu, ta) < 2:
                continue
            epicenter = eq_info.get("Epicenter", {})
            processed.append({
                "time":          quake_time.strftime("%Y-%m-%d %H:%M"),
                "location":      epicenter.get("Location", "不明"),
                "magnitude":     eq_info.get("Magnitude", {}).get("MagnitudeValue", 0),
                "depth":         eq_info.get("FocalDepth", 0),
                "hualien_level": str(hu),
                "yilan_level":   str(yi),
                "taitung_level": str(ta),
                "report_url":    quake.get("Web", ""),
            })
    except Exception as e:
        print(f"[earthquake] {e}")
    return processed


# ─────────────────────────────────────────────
# 颱風資料
# ─────────────────────────────────────────────
async def get_cwa_typhoon_data() -> Optional[Dict[str, Any]]:
    url = f"https://opendata.cwa.gov.tw/api/v1/rest/datastore/T-A0001-001?Authorization={CWA_API_KEY}"
    try:
        r = requests.get(url, verify=False, timeout=15)
        r.raise_for_status()
        warnings_data = (r.json().get("records", {})
                         .get("sea_typhoon_warning", {})
                         .get("typhoon_warning_summary", {})
                         .get("SeaTyphoonWarning"))
        if warnings_data:
            t = warnings_data[0]
            update_time = (datetime.fromisoformat(t["issue_time"])
                           .astimezone(TAIPEI_TZ).strftime("%m-%d %H:%M"))
            return {
                "name": t["typhoon_name"], "warning_type": t["warning_type"],
                "update_time": update_time, "location": t["center_location"],
                "wind_speed": t["max_wind_speed"],
                "status": t["warning_summary"]["content"],
                "img_url": "https://www.cwa.gov.tw/Data/typhoon/TY_NEWS/TY_NEWS_0.jpg",
            }
    except Exception as e:
        if getattr(getattr(e, 'response', None), 'status_code', None) != 404:
            print(f"[typhoon] {e}")
    return None


# ─────────────────────────────────────────────
# 蘇花公路路況（TDX）
# ─────────────────────────────────────────────
def get_tdx_access_token() -> Optional[str]:
    try:
        r = requests.post(
            "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token",
            data={"grant_type": "client_credentials", "client_id": TDX_APP_ID, "client_secret": TDX_APP_KEY},
            headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
        r.raise_for_status()
        return r.json().get("access_token")
    except Exception as e:
        print(f"❌ TDX token 失敗: {e}")
        return None

async def get_suhua_road_data() -> Dict[str, List[Dict[str, Any]]]:
    global cached_road_data, last_fetch_time
    if cached_road_data and (time.time() - last_fetch_time < CACHE_DURATION_SECONDS):
        return cached_road_data

    sections = {
        "蘇澳－南澳": ["蘇澳", "東澳", "蘇澳隧道", "東澳隧道", "東岳隧道"],
        "南澳－和平": ["南澳", "武塔", "漢本", "和平", "觀音隧道", "谷風隧道"],
        "和平－秀林": ["和平", "和仁", "崇德", "秀林", "中仁隧道", "和平隧道",
                    "和中隧道", "和中橋", "仁水隧道", "大清水隧道",
                    "錦文隧道", "匯德隧道", "崇德隧道", "清水斷崖", "下清水橋", "大清水"],
    }
    high_risk_kw  = ["封閉", "中斷", "坍方"]
    downgrade_kw  = ["改道", "替代道路", "行駛台9丁線", "單線雙向", "戒護通行", "放行"]
    mid_risk_kw   = ["落石", "施工", "管制", "事故", "壅塞", "車多", "濃霧", "作業"]
    partial_kw    = ["單線", "單側", "車道", "非全路幅", "慢車道", "機動"]
    new_suhua_lmk = ["蘇澳隧道", "東澳隧道", "觀音隧道", "谷風隧道", "中仁隧道", "仁水隧道"]
    new_suhua_km  = [(104, 113), (124, 145), (148, 160)]

    results = {name: [] for name in sections}
    token = get_tdx_access_token()
    if not token:
        err = {"section": "全線", "status": "認證失敗", "class": "road-red",
               "desc": "無法取得 TDX 授權", "time": "", "is_old_road": False, "detail_url": ""}
        for name in sections: results[name].append(err)
        return results

    try:
        r = requests.get(
            "https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Live/News/Highway"
            "?$orderby=PublishTime desc&$top=150&$format=JSON",
            headers={"Authorization": f"Bearer {token}"}, timeout=15)
        r.raise_for_status()
        suhua_news = [
            n for n in r.json().get("Newses", [])
            if "台9" in (n.get("Title", "") + n.get("Description", "")) or
               "蘇花" in (n.get("Title", "") + n.get("Description", ""))
        ]

        for news in suhua_news:
            title   = news.get("Title", "")
            desc    = news.get("Description", "")
            content = f"{title}：{desc}"
            if not desc: continue

            try:
                upd = datetime.fromisoformat(news.get("UpdateTime", "").replace("Z", "+00:00")).astimezone(TAIPEI_TZ)
                pub = datetime.fromisoformat(news.get("PublishTime", "").replace("Z", "+00:00")).astimezone(TAIPEI_TZ)
                time_str = f"更新：{upd.strftime('%m-%d %H:%M')}（首發：{pub.strftime('%m-%d %H:%M')}）"
            except:
                time_str = ""

            status = "事件"; css_class = "road-yellow"; is_high = False
            for kw in high_risk_kw:
                if kw in content:
                    status = kw; css_class = "road-red"; is_high = True; break
            if not is_high:
                for kw in mid_risk_kw:
                    if kw in content: status = kw; break
            if is_high:
                if any(k in content for k in partial_kw):
                    status = f"管制（{status}單線）"; css_class = "road-yellow"
                elif any(k in content for k in downgrade_kw):
                    status = f"管制（{status}改道）"; css_class = "road-yellow"

            is_old = False
            if not any(lmk in content for lmk in new_suhua_lmk):
                km_m = re.search(r'(\d+\.?\d*)[Kk]', content)
                if km_m:
                    try:
                        km = float(km_m.group(1))
                        is_old = not any(lo <= km <= hi for lo, hi in new_suhua_km)
                    except: is_old = "台9丁" in content
                else: is_old = "台9丁" in content

            classified = False
            for sname, keywords in sections.items():
                if any(kw in content for kw in keywords):
                    results[sname].append({
                        "section": sname, "status": status, "class": css_class,
                        "desc": f"【{title}】{desc}", "time": time_str,
                        "is_old_road": is_old, "detail_url": news.get("NewsURL", ""),
                    })
                    classified = True; break
            if not classified:
                results.setdefault("其他蘇花路段", []).append({
                    "section": "其他蘇花路段", "status": status, "class": css_class,
                    "desc": f"【{title}】{desc}", "time": time_str,
                    "is_old_road": is_old, "detail_url": news.get("NewsURL", ""),
                })

        cached_road_data = results
        last_fetch_time  = time.time()

    except Exception as e:
        print(f"❌ TDX 路況失敗: {e}")
        err = {"section": "全線", "status": "讀取失敗", "class": "road-red",
               "desc": "無法連線到 TDX 伺服器", "time": "", "is_old_road": False, "detail_url": ""}
        for name in sections: results[name].append(err)

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
