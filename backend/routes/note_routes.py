from flask import Blueprint, jsonify, request
from auth.user_auth import get_ms_token_from_session, get_session_user
from services import (load_all_notes, create_note, delete_note,
                      get_pending_notifications, update_note,
                      pause_note, resume_note)

note_bp = Blueprint("note", __name__, url_prefix="/api/notes")


@note_bp.get("")
def list_notes():
    """Trả về toàn bộ danh sách notes."""
    notes = load_all_notes()
    # Bỏ _file (đường dẫn nội bộ) trước khi trả về client
    clean = []
    for n in notes:
        c = {k: v for k, v in n.items() if not k.startswith("_")}
        c["stt"] = n.get("_stt", 0)
        clean.append(c)
    return jsonify(clean)


@note_bp.post("")
def add_note():
    """
    Tạo note mới.
    Body: {keyword, content, times, days, months, mode, delete_mode, repeat_count, repeat_interval, emails}
    """
    body = request.json or {}

    keyword         = body.get("keyword", "").strip()
    content         = body.get("content", "").strip()
    times           = body.get("times", [])
    days            = body.get("days", [])
    months          = body.get("months", [])
    mode            = body.get("mode", "1 lần")
    delete_mode     = body.get("delete_mode", "delete")
    repeat_count    = body.get("repeat_count", 1)
    repeat_interval = body.get("repeat_interval", 5)
    emails          = body.get("emails", [])

    if not keyword or not content:
        return jsonify({"error": "Thiếu keyword hoặc content"}), 400
    if not times or not days or not months:
        return jsonify({"error": "Thiếu times, days hoặc months"}), 400

    try:
        ms_token = get_ms_token_from_session()
        user = get_session_user()
        creator_email = user.get("email") if user else None
        
        note = create_note(
            keyword, content, times, days, months, mode, delete_mode,
            repeat_count=repeat_count, repeat_interval=repeat_interval,
            emails=emails, ms_token=ms_token, creator_email=creator_email
        )
        result = {k: v for k, v in note.items() if not k.startswith("_")}
        result["stt"] = note.get("_stt", 0)
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@note_bp.put("/<int:stt>")
def modify_note(stt: int):
    """
    Chỉnh sửa note theo STT.
    Body: {keyword, content, times, days, months, mode, delete_mode, repeat_count, repeat_interval, emails, paused}
    """
    body = request.json or {}

    keyword         = body.get("keyword", "").strip()
    content         = body.get("content", "").strip()
    times           = body.get("times", [])
    days            = body.get("days", [])
    months          = body.get("months", [])
    mode            = body.get("mode", "1 lần")
    delete_mode     = body.get("delete_mode", "delete")
    repeat_count    = body.get("repeat_count", 1)
    repeat_interval = body.get("repeat_interval", 5)
    emails          = body.get("emails", [])
    paused          = body.get("paused", False)

    if not keyword or not content:
        return jsonify({"error": "Thiếu keyword hoặc content"}), 400
    if not times or not days or not months:
        return jsonify({"error": "Thiếu times, days hoặc months"}), 400

    try:
        ms_token = get_ms_token_from_session()
        user = get_session_user()
        creator_email = user.get("email") if user else None
        
        note = update_note(
            stt, keyword, content, times, days, months, mode, delete_mode,
            repeat_count=repeat_count, repeat_interval=repeat_interval,
            emails=emails, paused=paused, ms_token=ms_token, creator_email=creator_email
        )
        result = {k: v for k, v in note.items() if not k.startswith("_")}
        result["stt"] = note.get("_stt", 0)
        return jsonify(result)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@note_bp.patch("/<int:stt>/pause")
def pause_reminder(stt: int):
    """Tạm dừng note theo STT."""
    if pause_note(stt):
        return jsonify({"paused": stt})
    return jsonify({"error": f"Không tìm thấy note {stt}"}), 404


@note_bp.patch("/<int:stt>/resume")
def resume_reminder(stt: int):
    """Bật lại note theo STT."""
    if resume_note(stt):
        return jsonify({"resumed": stt})
    return jsonify({"error": f"Không tìm thấy note {stt}"}), 404


@note_bp.delete("/<int:stt>")
def remove_note(stt: int):
    """Xóa note theo STT (số trong tên file remindersN.json)."""
    import os
    from config import NOTE_ARCHIVE_DIR

    fpath = os.path.join(NOTE_ARCHIVE_DIR, f"reminders{stt}.json")
    if delete_note(fpath, stt=stt, note_tag=f"note:{stt}"):
        return jsonify({"deleted": stt})
    return jsonify({"error": f"Không tìm thấy note {stt}"}), 404


@note_bp.get("/pending")
def pending_notifications():
    """Frontend poll endpoint này để nhận thông báo chờ xử lý.
    
    Luôn trả về nhanh (không hang) — nếu không lấy được lock trong 0.5s
    thì trả về danh sách rỗng để frontend thử lại sau.
    """
    try:
        notifications = get_pending_notifications()
        return jsonify(notifications)
    except Exception as e:
        print(f"ERROR get_pending_notifications: {e}")
        return jsonify([])  # Trả về mảng rỗng thay vì lỗi để không dừng poller

