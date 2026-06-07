import threading
import time
from flask import Blueprint, jsonify, request
from config import (NVL_REPORT_FORM_PATH, TQB_REPORT_FORM_PATH,
                    BDNC_REPORT_FORM_PATH, VG_REPORT_FORM_PATH, MDR_REPORT_FORM_PATH,
                    LACASTA_REPORT_FORM_PATH, HOTLINES_AND_CONFIRM_FORM_PATH)
from services import (sync_files_from_onedrive, get_report_text,
                      list_files_from_url, get_site_chart_data,
                      get_filtered_chart_data, get_comprehensive_dashboard_data)
from services.admin import load_sites_config
from datetime import datetime, date
import collections
import re

report_bp = Blueprint("report", __name__, url_prefix="/api")

# Cache danh sách files per site (load 1 lần sau sync)
_site_files_cache: dict = {}  # {site_key: (data, loaded_at)}
_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 5 phút

# Lock tránh chạy sync song song gây tràn RAM và ghi đè file
_sync_lock = threading.Lock()
_is_syncing = False


def _get_site_files(site_key: str) -> dict:
    """Lay va cache danh sach files cho mot site (TTL=5 phut)."""
    now = time.time()

    with _cache_lock:
        if site_key in _site_files_cache:
            data, loaded_at = _site_files_cache[site_key]
            if now - loaded_at < _CACHE_TTL:
                return data

    # Tim OneDrive path — thu ca ten day du lan ten viet tat
    onedrive_path = None
    sites_config, _ = load_sites_config()
    for group in sites_config.values():
        if site_key in group:
            onedrive_path = group[site_key]
            break
        # Thu uppercase
        for k, v in group.items():
            if k.upper() == site_key.upper():
                onedrive_path = v
                break
        if onedrive_path:
            break
    if not onedrive_path:
        return {}

    files  = list_files_from_url(onedrive_path)
    result = {}
    for f in files:
        label = f["name"].replace(".txt", "").replace(".TXT", "")
        result[label] = {"id": f["id"], "name": f["name"]}

    # Cache kết quả (kể cả rỗng, tránh gọi OneDrive liên tục khi folder trống)
    with _cache_lock:
        _site_files_cache[site_key] = (result, time.time())

    return result


# -----------------------------------------------------------
@report_bp.get("/sites")
def get_sites():
    """Trả về cấu trúc AEONMALL / MAXVALUE và map site key."""
    sites_config, site_key_map = load_sites_config()
    return jsonify({
        "sites": sites_config,
        "key_map": site_key_map
    })


@report_bp.get("/sites/<path:site_key>/items")
def get_site_items(site_key: str):
    """Trả về danh sách file (label + id) của một site."""
    try:
        items = _get_site_files(site_key)  # giu nguyen ten day du, khong upper
        if not items:
            return jsonify([])
        # Trả về list: [{label, file_id, file_name}]
        result = [
            {"label": label, "file_id": meta["id"], "file_name": meta["name"]}
            for label, meta in items.items()
        ]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@report_bp.post("/report/text")
def get_report():
    """
    Đọc nội dung file report.
    Body: {file_id, file_name, is_no_error (optional, default false)}
    """
    body        = request.json or {}
    file_id     = body.get("file_id", "")
    file_name   = body.get("file_name", "")
    is_no_error = body.get("is_no_error", False)
    raw         = body.get("raw", False)

    if not file_id or not file_name:
        return jsonify({"error": "Thiếu file_id hoặc file_name"}), 400

    try:
        text = get_report_text(file_id, file_name, is_no_error, raw)
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@report_bp.post("/sync")
def trigger_sync():
    """
    Trigger đồng bộ toàn bộ files từ OneDrive.
    Chạy background thread, trả về ngay lập tức.
    """
    global _is_syncing
    with _sync_lock:
        if _is_syncing:
            return jsonify({"error": "Tiến trình đồng bộ đang chạy, vui lòng thử lại sau.", "code": "already_syncing"}), 409
        _is_syncing = True

    def do_sync():
        global _is_syncing
        try:
            paths = [
                NVL_REPORT_FORM_PATH, TQB_REPORT_FORM_PATH,
                BDNC_REPORT_FORM_PATH, VG_REPORT_FORM_PATH,
                MDR_REPORT_FORM_PATH, LACASTA_REPORT_FORM_PATH,
                HOTLINES_AND_CONFIRM_FORM_PATH,
            ]
            for path in paths:
                try:
                    sync_files_from_onedrive(path)
                except Exception as e:
                    print(f"ERROR: Sync failed [{path}]: {e}")

            # Clear site cache sau khi sync
            with _cache_lock:
                _site_files_cache.clear()

            # FIX: Invalidate dashboard Excel cache sau sync để dữ liệu mới nhất được load
            try:
                from services.excel import _dashboard_cache, _load_dashboard_raw
                with _dashboard_cache["lock"]:
                    _dashboard_cache["loaded_at"] = 0.0  # Expire cache ngay
                _load_dashboard_raw()
            except Exception as e:
                print(f"WARN: Dashboard cache invalidation failed: {e}")
        finally:
            with _sync_lock:
                _is_syncing = False

    threading.Thread(target=do_sync, daemon=True).start()
    return jsonify({"message": "Đang đồng bộ ở background..."})


@report_bp.get("/charts/data")
def get_charts_data():
    """
    Trả về dữ liệu biểu đồ cho sheet SITE_DATA.
    """
    try:
        return jsonify(get_site_chart_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@report_bp.get("/charts/filtered")
def get_filtered_charts_data():
    """
    Trả về dữ liệu biểu đồ được lọc theo ngày.
    Query params: start, end, site (optional)
    """
    start_date = request.args.get("start")
    end_date   = request.args.get("end")
    site       = request.args.get("site")

    if not start_date or not end_date:
        return jsonify({"error": "Thiếu start_date hoặc end_date"}), 400

    try:
        return jsonify(get_filtered_chart_data(start_date, end_date, site))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@report_bp.get("/dashboard/data")
def get_dashboard_full_data():
    """
    Trả về toàn bộ dữ liệu thống kê cho Dashboard chuyên nghiệp.
    Query params: start, end (YYYY-MM-DD)
    """
    start = request.args.get("start")
    end   = request.args.get("end")
    site  = request.args.get("site")
    try:
        return jsonify(get_comprehensive_dashboard_data(start, end, site))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def prewarm_site_files_cache():
    """Nạp trước danh sách file của toàn bộ site ở background khi app khởi chạy."""
    def run():
        time.sleep(8)  # Đợi app khởi động ổn định
        try:
            sites_config, _ = load_sites_config()
            all_keys = []
            for group in sites_config.values():
                for site_key in group.keys():
                    all_keys.append(site_key)
            print(f"[PREWARM] Bắt đầu nạp trước site files cache cho {len(all_keys)} sites...", flush=True)
            for site_key in all_keys:
                try:
                    _get_site_files(site_key)
                except Exception as ex:
                    print(f"[PREWARM] Không thể pre-warm cache cho site {site_key}: {ex}", flush=True)
            print("[PREWARM] Đã hoàn thành nạp trước toàn bộ site files cache.", flush=True)
        except Exception as e:
            print(f"[PREWARM] Lỗi trong quá trình pre-warm site files cache: {e}", flush=True)

    threading.Thread(target=run, daemon=True).start()