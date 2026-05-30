import os
import sys
import datetime
import threading
import traceback
from flask import Blueprint, jsonify, request
from config import HOTLINES_AND_CONFIRM_FORM_PATH, REPORT_FORM_DIR
from services import list_files_from_url, download_file
from services.report import (fill_contact_template, fill_status_template,
                              fill_notification_template)
from services.excel import append_status_to_excel

contact_bp = Blueprint("contact", __name__, url_prefix="/api")

# ── Template cache ──────────────────────────────────────────────────────────
# Cache templates trong bộ nhớ để tránh gọi OneDrive mỗi request.
# Cache được xóa sau 10 phút hoặc khi template không tồn tại local.
_template_cache: dict = {}     # {keyword: (content, loaded_at)}
_CACHE_TTL_SECONDS = 600       # 10 phút
_template_lock = threading.Lock()


def _load_template(keyword: str) -> str:
    """Tải template từ cache hoặc OneDrive. Dùng lock để tránh race condition."""
    import time

    with _template_lock:
        cached = _template_cache.get(keyword)
        if cached:
            content, loaded_at = cached
            if time.time() - loaded_at < _CACHE_TTL_SECONDS:
                return content
            # Cache đã hết hạn, xóa để load lại
            del _template_cache[keyword]

    # Load từ OneDrive (ngoài lock để không block các request khác)
    try:
        files = list_files_from_url(HOTLINES_AND_CONFIRM_FORM_PATH)
        target_file = next((f for f in files if keyword in f["name"]), None)
        if not target_file:
            raise FileNotFoundError(f"Khong tim thay template '{keyword}'")
        local_path = download_file(target_file, save_dir=REPORT_FORM_DIR)
        if not local_path:
            raise FileNotFoundError(f"Tai template '{keyword}' that bai")
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Lưu vào cache
        with _template_lock:
            import time as _t
            _template_cache[keyword] = (content, _t.time())
        return content
    except Exception:
        # Fallback: thử đọc file local đã cache trước đó (nếu có)
        for fname in os.listdir(REPORT_FORM_DIR):
            if keyword in fname:
                local_path = os.path.join(REPORT_FORM_DIR, fname)
                try:
                    with open(local_path, "r", encoding="utf-8") as f:
                        return f.read()
                except Exception:
                    pass
        raise


def _log(msg):
    from config import DEBUG_LOG_PATH
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg, flush=True)
    try:
        log_dir = os.path.dirname(DEBUG_LOG_PATH)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(full_msg + "\n")
    except:
        pass
    sys.stdout.flush()


@contact_bp.post("/contact")
def contact():
    body      = request.json or {}
    confirmed = body.get("confirmed", True)
    if confirmed:
        return jsonify({"text": ""})
    dept   = body.get("dept", "")
    device = body.get("device", "")
    status = body.get("status", "")
    desc   = body.get("desc", "")
    try:
        template = _load_template("CONFIRM_FORM")
        text     = fill_contact_template(template, dept, device, status, desc)
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@contact_bp.post("/status")
def status_form():
    body        = request.json or {}
    confirmed   = body.get("confirmed", True)

    if confirmed:
        return jsonify({"text": "", "excel": None})

    dept        = body.get("dept", "")
    device      = body.get("device", "")
    pic         = body.get("pic", "")
    alarm_type  = body.get("alarm_type", "")
    alarm_level = body.get("alarm_level", "")
    status      = body.get("status", "")
    processing  = body.get("processing", "")
    week        = body.get("week", "")
    start_time  = body.get("start_time", "")
    start_date  = body.get("start_date", "")
    end_time    = body.get("end_time", "")
    end_date    = body.get("end_date", "")
    desc        = body.get("desc", "")

    _log(f"[STATUS] dept={dept} device={device} pic={pic} alarm={alarm_type} status={status}")

    # Tinh thoi gian xu ly
    time_process = ""
    if start_time and end_time:
        try:
            fmt      = "%H:%M"
            start_dt = datetime.datetime.strptime(start_time, fmt)
            end_dt   = datetime.datetime.strptime(end_time, fmt)
            delta    = end_dt - start_dt
            total_m  = int(delta.total_seconds() / 60)
            if total_m < 0:
                total_m += 1440
            h, m     = divmod(total_m, 60)
            time_process = f"{h} gio {m} phut" if h else f"{m} phut"
        except ValueError:
            time_process = ""

    # Fill template
    text = ""
    try:
        template = _load_template("CONFIRM_FORM")
        text     = fill_status_template(template, dept, device, status, time_process, desc)
    except Exception as e:
        text = f"[Loi template] {e}"

    # Ghi Excel — KHONG dung daemon thread de tranh bi kill
    def write_excel():
        _log("[EXCEL] Starting write...")
        try:
            result = append_status_to_excel(
                site_name   = dept,
                device      = device,
                pic         = pic,
                alarm_type  = alarm_type,
                alarm_level = alarm_level,
                reason      = f"{start_time} - {end_time}" if start_time else desc,
                start_time  = start_time,
                start_date  = start_date,
                end_time    = end_time,
                end_date    = end_date,
                status      = status,
                description = desc,
                processing  = processing,
                week        = week,
            )
            _log(f"[EXCEL] OK - row={result['row']}")
        except Exception:
            _log(f"[EXCEL] ERROR:\n{traceback.format_exc()}")

    # Ghi Excel trong background — dùng daemon=True để không block Flask worker
    # Response được trả về client ngay lập tức, không chờ Excel ghi xong
    t = threading.Thread(target=write_excel, daemon=True)
    t.start()

    return jsonify({"text": text, "excel": "writing"})


@contact_bp.post("/notification")
def notification_form():
    body        = request.json or {}
    site        = body.get("site", "")
    description = body.get("description", "")
    start_time  = body.get("start_time", "")
    start_date  = body.get("start_date", "")
    end_time    = body.get("end_time", "")
    end_date    = body.get("end_date", "")
    devices     = body.get("devices", "")
    note        = body.get("note", "")
    try:
        template = _load_template("NOTIFICATION_FORM")
        text     = fill_notification_template(
            template, site, description,
            start_time, start_date,
            end_time, end_date,
            devices, note
        )
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500