from flask import Blueprint, jsonify, request
from services import (load_all_notes, create_note, delete_note,
                      get_pending_notifications)

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
    Body: {keyword, content, times, days, months, mode, delete_mode}
    """
    body = request.json or {}

    keyword     = body.get("keyword", "").strip()
    content     = body.get("content", "").strip()
    times       = body.get("times", [])
    days        = body.get("days", [])
    months      = body.get("months", [])
    mode        = body.get("mode", "1 lần")
    delete_mode = body.get("delete_mode", "delete")

    if not keyword or not content:
        return jsonify({"error": "Thiếu keyword hoặc content"}), 400
    if not times or not days or not months:
        return jsonify({"error": "Thiếu times, days hoặc months"}), 400

    try:
        note = create_note(keyword, content, times, days, months, mode, delete_mode)
        result = {k: v for k, v in note.items() if not k.startswith("_")}
        result["stt"] = note.get("_stt", 0)
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
