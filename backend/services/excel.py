import os
import base64
import datetime
import requests
import threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import sys
import traceback
import time as _time
import re
from auth import graph_session
from services.admin import load_sites_config
from config import CHART_EXCEL_SHARE_LINK, STATUS_EXCEL_SHARE_LINK, BASE_DIR

# Session dùng chung với connection pool và retry strategy (không retry cho 429 để tránh vòng lặp)
_session = requests.Session()
_retry = Retry(total=1, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504], raise_on_status=False)
_session.mount("https://", HTTPAdapter(max_retries=_retry, pool_connections=4, pool_maxsize=8))

# Cache for drive and item IDs
_chart_excel_cache: dict = {"drive_id": None, "item_id": None}
_status_excel_cache: dict = {"drive_id": None, "item_id": None}

# ============================================================
# FIX: In-memory dashboard data cache
# Tránh gọi OneDrive mỗi request → nguyên nhân chính gây "Waiting"
# TTL mặc định 5 phút; tự động background-refresh khi sắp hết hạn
# ============================================================
_dashboard_cache: dict = {
    "data": None,         # kết quả cuối cùng
    "loaded_at": 0.0,     # epoch timestamp khi load xong
    "is_loading": False,  # đang có thread nào load không
    "lock": threading.Lock(),
}
_DASHBOARD_CACHE_TTL = 300      # 5 phút: trả cache nếu còn mới
_DASHBOARD_REFRESH_AHEAD = 60   # Bắt đầu background-refresh khi còn 60s nữa hết hạn


def _log(msg):
    from config import DEBUG_LOG_PATH
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    try:
        print(full_msg, flush=True)
    except Exception:
        try:
            print(full_msg.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"), flush=True)
        except Exception:
            pass
    try:
        log_dir = os.path.dirname(DEBUG_LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")
    except: pass
    sys.stdout.flush()


def _to_int(value):
    try:
        if value is None or value == "": return 0
        return int(float(value))
    except: return 0


def _resolve_excel_item(share_link: str = CHART_EXCEL_SHARE_LINK, cache: dict = None):
    if cache is None: cache = _chart_excel_cache
    if cache["drive_id"] and cache["item_id"]: return cache["drive_id"], cache["item_id"]
    token = graph_session.ensure_token()
    headers = {"Authorization": f"Bearer {token}"}
    clean_link = share_link.strip().split("?")[0]
    encoded = base64.b64encode(clean_link.encode("utf-8")).decode("utf-8").rstrip("=").replace("/", "_").replace("+", "-")
    r = _session.get(f"https://graph.microsoft.com/v1.0/shares/u!{encoded}/driveItem", headers=headers, timeout=15)
    if r.status_code != 200: raise Exception(f"Resolve failed: {r.status_code}")
    data = r.json()
    cache["drive_id"] = data["parentReference"]["driveId"]
    cache["item_id"]  = data["id"]
    return cache["drive_id"], cache["item_id"]


def _parse_date(val):
    if not val: return None
    try:
        if isinstance(val, (int, float)):
            return datetime.datetime(1899, 12, 30) + datetime.timedelta(days=val)
        s = str(val).strip()
        for fmt in ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y"]:
            try: return datetime.datetime.strptime(s.split(' ')[0], fmt)
            except: continue
    except: pass
    return None

def _parse_hour(val):
    if val is None or val == "": return 0
    try:
        if isinstance(val, (int, float)): return int((val * 24) % 24)
        s = str(val).strip().upper()
        for fmt in ["%I:%M:%S %p", "%I:%M %p", "%H:%M:%S", "%H:%M"]:
            try: return datetime.datetime.strptime(s, fmt).hour
            except: continue
    except: pass
    return 0


def append_status_to_excel(site_name, device, pic, alarm_type="", alarm_level="", reason="", start_time="", start_date="", end_time="", end_date="", status="", description="", processing="", week=""):
    drive_id, item_id = _resolve_excel_item(STATUS_EXCEL_SHARE_LINK, _status_excel_cache)
    try:
        now = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
        def f_dt(d):
            if not d: return f"{now.month}/{now.day}/{now.year}"
            try: 
                parsed = datetime.datetime.strptime(d, "%Y-%m-%d")
                return f"{parsed.month}/{parsed.day}/{parsed.year}"
            except: return d
        s_date_fmt = f_dt(start_date)
        e_date_fmt = f_dt(end_date) if end_date else s_date_fmt

        def _fmt_t(t):
            if not t: return ""
            try: return datetime.datetime.strptime(t, "%H:%M").strftime("%H:%M")
            except: return t
        start_norm = _fmt_t(start_time)
        end_norm   = _fmt_t(end_time)

        d_min = 0; t_type = "Daytime"
        try:
            # Tính t_type độc lập dựa trên giờ theo đúng logic Excel: 
            # =IF(OR(Time > TIME(22,0,0), Time < TIME(6,0,0)),"Nighttime","Daytime")
            st_time_obj = datetime.datetime.strptime(start_time, "%H:%M").time()
            if st_time_obj > datetime.time(22, 0, 0) or st_time_obj < datetime.time(6, 0, 0):
                t_type = "Nighttime"
            else:
                t_type = "Daytime"
        except: pass

        try:
            fmt = "%Y-%m-%d %H:%M"
            st = datetime.datetime.strptime(f"{start_date} {start_time}", fmt)
            et = datetime.datetime.strptime(f"{end_date} {end_time}", fmt)
            if et > st:
                diff = et - st
                d_min = int(diff.total_seconds() / 60)
        except: pass

        _, site_key_map = load_sites_config()
        sc = site_key_map.get(site_name.upper(), site_name)
        rem = description if description else reason

        token = graph_session.ensure_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        target = "Processing Results"
        r_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets"
        sheets_r = requests.get(r_url, headers=headers, timeout=20)
        if sheets_r.status_code == 200:
            sn_list = [s["name"] for s in sheets_r.json().get("value", [])]
            for sn in sn_list:
                if sn.strip().upper() == "PROCESSING RESULTS": target = sn; break
            else:
                if "Sheet1" in sn_list: target = "Sheet1"
                else: target = sn_list[0]

        r_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets('{target}')/usedRange(valuesOnly=true)"
        r_range = requests.get(r_url, headers=headers, timeout=20)
        if r_range.status_code != 200:
            # Fallback nếu valuesOnly không được hỗ trợ hoặc sheet trống
            r_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets('{target}')/usedRange"
            r_range = requests.get(r_url, headers=headers, timeout=20)
            
        data = r_range.json()
        addr = data.get("address", "")
        
        # Tìm dòng cuối cùng từ address (ví dụ: Sheet1!A1:N100 -> lấy 100)
        m = re.search(r'[A-Za-z]+(\d+)$', addr)
        if m:
            l_row = int(m.group(1))
        else:
            # Fallback nếu address chỉ có 1 ô (Sheet1!A1 -> lấy 1)
            m_single = re.search(r'!?[A-Za-z]+(\d+)$', addr)
            l_row = int(m_single.group(1)) if m_single else 1
            
        n_row = l_row + 1

        row_v = [
            sc,           # A: Site
            week,         # B: Week
            s_date_fmt,   # C: Start Date
            device,       # D: Device
            status,       # E: Status
            rem,          # F: Reason (Mô tả)
            alarm_type,   # G: Alarm Type
            d_min,        # H: Duration
            t_type,       # I: Daytime/Nighttime
            start_norm,   # J: Start Time
            end_norm,     # K: End Time
            alarm_level,  # L: Alarm Level
            e_date_fmt,   # M: End Date
            pic           # N: PIC
        ]
        
        # Chuyển các chuỗi rỗng thành None (tương đương null trong JSON) để Graph API không ghi đè hàm
        row_v = [val if val != "" else None for val in row_v]

        p_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets('{target}')/range(address='A{n_row}:N{n_row}')"
        requests.patch(p_url, headers=headers, json={"values": [row_v]}, timeout=20)
        
        # Center align the row
        requests.patch(p_url + "/format", headers=headers, json={
            "horizontalAlignment": "Center", 
            "verticalAlignment": "Center"
        }, timeout=20)
        
        return {"row": n_row, "site": site_name}
    except Exception:
        _log(traceback.format_exc()); raise


def get_excel_data() -> list:
    from config import METADATA_DIR
    import json
    
    try:
        drive_id, item_id = _resolve_excel_item()
        token = graph_session.ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        target = "Processing Results"
        r_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets"
        sheets_r = requests.get(r_url, headers=headers, timeout=15)
        if sheets_r.status_code == 200:
            sn_list = [s["name"] for s in sheets_r.json().get("value", [])]
            for sn in sn_list:
                if sn.strip().upper() == "PROCESSING RESULTS": target = sn; break
            else:
                if "Sheet1" in sn_list: target = "Sheet1"
                else: target = sn_list[0]
        
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets('{target}')/usedRange"
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200: return []
        res_json = r.json()
        vals = res_json.get("values", [])
        address = res_json.get("address", "")
        
        # Save cache
        try:
            cache_file = os.path.join(METADATA_DIR, "excel_data_processed_cache.json")
            col_match = re.search(r'(?:.*!)?([A-Z]+)', address)
            s_idx = col_to_idx(col_match.group(1)) if col_match else 0
            
            data = []
            for row in vals:
                if not row: continue
                def gv(i):
                    off = i - s_idx
                    return row[off] if 0 <= off < len(row) else None
                sc = str(gv(0) or "").strip().upper()
                if not sc or sc in ["SITE", "SITE CODE"]: continue
                dt = _parse_date(gv(2))
                if not dt: continue
                data.append({
                    "site_code": sc, "date": dt.strftime("%m/%d/%Y"),
                    "device": str(gv(3) or ""), "status": str(gv(4) or ""),
                    "severity": str(gv(11) or ""), "duration": str(gv(7) or "0"), "pic": str(gv(13) or "")
                })
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return data
        except Exception as ce:
            _log(f"WARN: Error writing get_excel_data cache: {ce}")
            
    except Exception as e:
        _log(f"WARN: get_excel_data OneDrive error ({e}), loading from local cache...")
        cache_file = os.path.join(METADATA_DIR, "excel_data_processed_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as ce:
                _log(f"ERROR: Cannot read get_excel_data cache: {ce}")
        return []

def col_to_idx(col):
    idx = 0
    for char in col: idx = idx * 26 + (ord(char) - ord('A') + 1)
    return idx - 1

def _load_dashboard_raw():
    """Tải raw Excel data từ OneDrive, cập nhật _dashboard_cache.
    Gọi trong background thread — không block request."""
    from config import METADATA_DIR
    import json

    with _dashboard_cache["lock"]:
        if _dashboard_cache["is_loading"]:
            return  # thread khác đang load, bỏ qua
        _dashboard_cache["is_loading"] = True

    try:
        drive_id, item_id = _resolve_excel_item(CHART_EXCEL_SHARE_LINK, _chart_excel_cache)
        token   = graph_session.ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        target  = "Processing Results"

        r_url    = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets"
        sheets_r = _session.get(r_url, headers=headers, timeout=15)
        if sheets_r.status_code == 200:
            sn_list = [s["name"] for s in sheets_r.json().get("value", [])]
            for sn in sn_list:
                if sn.strip().upper() == "PROCESSING RESULTS":
                    target = sn
                    break
            else:
                target = "Sheet1" if "Sheet1" in sn_list else (sn_list[0] if sn_list else target)

        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
            f"/workbook/worksheets('{target}')/usedRange"
        )
        r = _session.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            raise Exception(f"usedRange HTTP {r.status_code}")

        res_json = r.json()
        vals     = res_json.get("values", [])
        address  = res_json.get("address", "")

        # Lưu cache disk để dùng khi offline
        try:
            os.makedirs(METADATA_DIR, exist_ok=True)
            cache_file = os.path.join(METADATA_DIR, "excel_raw_cache.json")
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"values": vals, "address": address}, f, ensure_ascii=False, indent=2)
            _log("OK: Updated Excel data cache (disk).")
        except Exception as ce:
            _log(f"WARN: Error saving Excel disk cache: {ce}")

        with _dashboard_cache["lock"]:
            _dashboard_cache["data"]      = {"values": vals, "address": address}
            _dashboard_cache["loaded_at"] = _time.time()

        _log("OK: Dashboard in-memory cache refreshed.")

    except Exception as e:
        _log(f"WARN: Background Excel refresh failed: {e}")
        # Fallback: cố gắng đọc disk cache
        from config import METADATA_DIR
        import json
        cache_file = os.path.join(METADATA_DIR, "excel_raw_cache.json")
        if os.path.exists(cache_file) and _dashboard_cache["data"] is None:
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                with _dashboard_cache["lock"]:
                    _dashboard_cache["data"]      = cached
                    _dashboard_cache["loaded_at"] = _time.time() - _DASHBOARD_CACHE_TTL + 30
                _log("OK: Dashboard restored from disk cache (fallback).")
            except Exception as ce:
                _log(f"ERROR: Cannot read disk cache: {ce}")
    finally:
        with _dashboard_cache["lock"]:
            _dashboard_cache["is_loading"] = False


def _get_raw_excel_data() -> dict:
    """Trả về raw Excel data từ in-memory cache.
    Tự động trigger background refresh khi cache sắp hết hạn.
    Nếu chưa có cache, BLOCK một lần để tải về (cold start)."""
    now     = _time.time()
    age     = now - _dashboard_cache["loaded_at"]
    has_data = _dashboard_cache["data"] is not None

    if has_data:
        # Cache đã có dữ liệu -> TRẢ THẲNG NGAY để không block UI của user.
        # Nếu cache đã đến lúc cần làm mới (lớn hơn TTL - REFRESH_AHEAD, hoặc đã quá TTL),
        # ta kích hoạt làm mới ở background thread.
        if age >= (_DASHBOARD_CACHE_TTL - _DASHBOARD_REFRESH_AHEAD):
            with _dashboard_cache["lock"]:
                if not _dashboard_cache["is_loading"]:
                    threading.Thread(target=_load_dashboard_raw, daemon=True).start()
        return _dashboard_cache["data"]

    # Chỉ block duy nhất một lần đầu khi hoàn toàn chưa có cache (cold start)
    _load_dashboard_raw()
    return _dashboard_cache["data"] or {"values": [], "address": ""}


def get_site_chart_data(): return get_comprehensive_dashboard_data()
def get_filtered_chart_data(s, e, si=None): return get_comprehensive_dashboard_data(s, e, si)

def get_comprehensive_dashboard_data(start_date=None, end_date=None, site_filter=None):
    # FIX: Dùng cache thay vì gọi thẳng OneDrive mỗi request
    raw = _get_raw_excel_data()
    vals    = raw.get("values", [])
    address = raw.get("address", "")

    if not vals:
        return {"error": "Không có dữ liệu. Vui lòng đợi cache tải hoặc thử lại sau."}

    # 2. Xử lý dữ liệu từ cache
    try:
        from services.admin import load_sites_config
        _, site_map = load_sites_config()
        c2n = {v.upper(): k for k, v in site_map.items()}
        n2c = {k.upper(): v.upper() for k, v in site_map.items()}
        for k, v in site_map.items():
            short = k.split(' ')[-1].upper()
            if short not in n2c: n2c[short] = v.upper()

        extra_variants = {
            "ABNC": "AEON Binh Duong NC", "TQB": "AEON Ta Quang Buu", "MIDORI": "AEON Midori",
            "NVL": "AEON Nguyen Van Linh", "VG": "AEON Van Giang", "ABDNC": "AEON Binh Duong NC",
            "ATQB": "AEON Ta Quang Buu", "AMDR": "AEON Midori", "ANVL": "AEON Nguyen Van Linh", "AVG": "AEON Van Giang"
        }
        for v, c in extra_variants.items():
            k_u = c.upper().strip()
            if k_u in n2c: n2c[v] = n2c[k_u]

        col_match = re.search(r'(?:.*!)?([A-Z]+)', address)
        s_idx = col_to_idx(col_match.group(1)) if col_match else 0
        
        s_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        e_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
        
        import collections
        total_alarms = 0; total_downtime = 0; active_alarms = 0; resolved_alarms = 0; critical_alarms = 0
        trends = {}; sev_c = {"High": 0, "Medium": 0, "Low": 0}; site_s = {}; top_d = {}; dev_t = {}; heatmap_data = {}; table = collections.deque(maxlen=50)
        
        for row in vals:
            if not row: continue
            def gv(i):
                off = i - s_idx
                return row[off] if 0 <= off < len(row) else None
            sc_raw = str(gv(0) or "").strip().upper()
            if not sc_raw or sc_raw in ["SITE", "SITE CODE"]: continue
            sc = n2c.get(sc_raw, sc_raw)
            site_display = c2n.get(sc, sc_raw)
            if site_filter:
                f_sc = site_map.get(site_filter.upper(), site_filter).upper()
                if sc != f_sc: continue

            dt = _parse_date(gv(2))
            if not dt: continue
            if s_dt and dt < s_dt: continue
            if e_dt and dt > e_dt: continue

            d_str = dt.strftime("%Y-%m-%d"); weekday = dt.weekday()
            hour = _parse_hour(gv(9))
            downtime = _to_int(gv(7))
            
            total_alarms += 1; total_downtime += downtime
            status_l = str(gv(4) or "").lower()
            if status_l in ["done", "xử lý xong", "ok"]: resolved_alarms += 1
            else: active_alarms += 1

            trends[d_str] = trends.get(d_str, 0) + 1
            sev = str(gv(11) or "Low").capitalize()
            if sev in sev_c: sev_c[sev] += 1
            else: sev_c["Low"] += 1
            if sev == "High": critical_alarms += 1

            if sc not in site_s: site_s[sc] = {"count": 0, "downtime": 0, "devices": {}}
            site_s[sc]["count"] += 1; site_s[sc]["downtime"] += downtime
            dn = str(gv(3) or "Unknown")
            site_s[sc]["devices"][dn] = site_s[sc]["devices"].get(dn, 0) + 1
            top_d[dn] = top_d.get(dn, 0) + 1
            
            d_upper = dn.upper()
            dtp = "Other"
            if any(x in d_upper for x in ["HVAC", "AIR", "ĐIỀU HÒA"]): dtp = "HVAC"
            elif any(x in d_upper for x in ["SHOWCASE", "TỦ"]): dtp = "Showcase"
            elif any(x in d_upper for x in ["FREEZER", "ĐÔNG"]): dtp = "Freezer"
            elif any(x in d_upper for x in ["LIGHT", "ĐÈN"]): dtp = "Lighting"
            elif any(x in d_upper for x in ["REFRIG", "LẠNH"]): dtp = "Refrigeration"
            
            dev_t[dtp] = dev_t.get(dtp, 0) + 1
            heatmap_data[(weekday, hour)] = heatmap_data.get((weekday, hour), 0) + 1
            
            raw_time = gv(9)
            if isinstance(raw_time, (int, float)):
                total_minutes = round(raw_time * 24 * 60)
                h = (total_minutes // 60) % 24
                m = total_minutes % 60
                time_str = f"{h:02d}:{m:02d}:00"
            else:
                time_str = str(raw_time or "")
            
            table.append({
                "time": dt.strftime("%Y-%m-%d") + " " + time_str,
                "site": site_display, "device": dn, "severity": sev.lower(),
                "duration": downtime, "status": str(gv(4) or ""), "pic": str(gv(13) or "")
            })

        mttr = total_downtime / resolved_alarms if resolved_alarms > 0 else 0
        site_rankings = sorted(site_s.items(), key=lambda x: x[1]["count"], reverse=True)
        top_devices = sorted(top_d.items(), key=lambda x: x[1], reverse=True)[:10]
        
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; h_s = []
        for di, dn in enumerate(days):
            rd = [{"x": str(h), "y": heatmap_data.get((di, h), 0)} for h in range(24)]
            h_s.append({"name": dn, "data": rd})
            
        return {
            "kpis": {
                "total_alarms": total_alarms, "total_downtime": round(total_downtime / 60, 1),
                "active_alarms": active_alarms, "resolved_alarms": resolved_alarms,
                "critical_alarms": critical_alarms, "mttr": round(mttr, 1),
                "top_site": site_rankings[0][0] if site_rankings else "N/A"
            },
            "trends": {"daily": sorted([{"date": k, "count": v} for k, v in trends.items()], key=lambda x: x["date"])},
            "site_stats": [{"name": c2n.get(k, k), "code": k, "count": v["count"], "downtime": v["downtime"], "devices": v["devices"]} for k, v in site_rankings],
            "top_devices": [{"name": k, "count": v} for k, v in top_devices],
            "severity": sev_c, "heatmap": h_s,
            "device_types": [{"type": k, "count": v} for k, v in dev_t.items()],
            "table": list(table)[::-1]
        }
    except Exception as e:
        _log(traceback.format_exc()); return {"error": str(e)}
