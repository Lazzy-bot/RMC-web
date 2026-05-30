import os
import json
import datetime
import threading
import schedule
import time
from config import NOTE_ARCHIVE_DIR

# Danh sách các reminder đang hoạt động (pending notifications)
_pending_notifications = []
_notifications_lock    = threading.Lock()

# Schedule runner
_schedule_thread_started = False


def _start_schedule_runner():
    global _schedule_thread_started
    if _schedule_thread_started:
        return
    _schedule_thread_started = True

    def run():
        while True:
            schedule.run_pending()
            time.sleep(1)

    threading.Thread(target=run, daemon=True).start()


def _note_tag(note: dict | None = None, stt: int | None = None) -> str:
    if note is not None:
        if note.get("_tag"):
            return note["_tag"]
        if note.get("_stt") is not None:
            return f"note:{note['_stt']}"
    if stt is not None:
        return f"note:{stt}"
    return "note:unknown"


def _cancel_note_schedules(tag: str) -> None:
    schedule.clear(tag)


def _purge_pending_notifications(tag: str) -> None:
    with _notifications_lock:
        _pending_notifications[:] = [
            item for item in _pending_notifications
            if item.get("note_tag") != tag
        ]


# ---------------------------------------------------------------
def _get_next_stt() -> int:
    used = []
    for fname in os.listdir(NOTE_ARCHIVE_DIR):
        if fname.startswith("reminders") and fname.endswith(".json"):
            try:
                n = int(fname.replace("reminders", "").replace(".json", ""))
                used.append(n)
            except:
                pass
    n = 1
    while n in used:
        n += 1
    return n


def load_all_notes() -> list:
    """Đọc tất cả file remindersN.json trong NOTE_ARCHIVE_DIR."""
    result = []
    if not os.path.exists(NOTE_ARCHIVE_DIR):
        return result

    for fname in sorted(os.listdir(NOTE_ARCHIVE_DIR)):
        if not (fname.startswith("reminders") and fname.endswith(".json")):
            continue
        fpath = os.path.join(NOTE_ARCHIVE_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "keyword" in data:
                data["_file"] = fpath
                data["_stt"]  = int(fname.replace("reminders", "").replace(".json", ""))
                data["_tag"]  = _note_tag(data)
                if "delete_mode" not in data:
                    data["delete_mode"] = "delete"
                if "done" not in data:
                    data["done"] = False
                result.append(data)
        except Exception as e:
            print(f"ERROR reading {fname}: {e}")

    result.sort(key=lambda d: d.get("_stt", 0))
    return result


def create_note(keyword: str, content: str, times: list, days: list,
                months: list, mode: str, delete_mode: str = "delete") -> dict:
    """Tạo note mới, lưu file JSON, và lên lịch."""
    stt   = _get_next_stt()
    fpath = os.path.join(NOTE_ARCHIVE_DIR, f"reminders{stt}.json")

    data = {
        "keyword":     keyword,
        "content":     content,
        "times":       times,
        "days":        days,
        "months":      months,
        "mode":        mode,
        "delete_mode": delete_mode,
        "done":        False,
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    data["_file"] = fpath
    data["_stt"]  = stt
    data["_tag"]  = _note_tag(stt=stt)

    schedule_note(data)
    return data


def delete_note(file_path: str, stt: int | None = None, note_tag: str | None = None) -> bool:
    """Xóa file note và hủy toàn bộ lịch liên quan."""
    tag = note_tag or _note_tag(stt=stt)
    try:
        had_schedules = bool(tag and tag != "note:unknown" and schedule.get_jobs(tag))
        if tag and tag != "note:unknown":
            _cancel_note_schedules(tag)
            _purge_pending_notifications(tag)
        removed_file = False
        if os.path.exists(file_path):
            os.remove(file_path)
            removed_file = True
        return removed_file or had_schedules
    except Exception as e:
        print(f"ERROR deleting note: {e}")
    return False


def schedule_note(note: dict):
    """Lên lịch nhắc cho một note."""
    _start_schedule_runner()

    keyword     = note["keyword"]
    content     = note["content"]
    times       = note["times"]
    days        = note["days"]
    months      = note["months"]
    mode        = note["mode"]
    delete_mode = note.get("delete_mode", "delete")
    file_path   = note.get("_file")
    note_tag    = _note_tag(note)

    # Convert time tu UTC+7 sang UTC de schedule dung gio
    def to_utc(t_str):
        try:
            h, m = map(int, t_str.split(":"))
            total = h * 60 + m - 7 * 60  # tru 7 tieng
            total = total % (24 * 60)     # wrap qua ngay
            return f"{total // 60:02d}:{total % 60:02d}"
        except:
            return t_str

    for t in times:
        t_utc = to_utc(t)
        def make_job(t=t, t_utc=t_utc):
            def job():
                # Kiem tra ngay/thang theo gio Viet Nam (UTC+7)
                now = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
                if str(now.day) not in days or str(now.month) not in months:
                    return

                # Đẩy notification vào queue để frontend poll
                with _notifications_lock:
                    _pending_notifications.append({
                        "keyword": keyword,
                        "content": content,
                        "time":    t,
                        "note_tag": note_tag,
                    })

                if mode == "1 lần":
                    if file_path and os.path.exists(file_path):
                        try:
                            if delete_mode == "delete":
                                os.remove(file_path)
                            else:
                                with open(file_path, "r", encoding="utf-8") as f:
                                    d = json.load(f)
                                d["done"] = True
                                with open(file_path, "w", encoding="utf-8") as f:
                                    json.dump(d, f, ensure_ascii=False, indent=4)
                        except Exception as e:
                            print(f"ERROR post-reminder file handling: {e}")
                    return schedule.CancelJob

            return job

        schedule.every().day.at(t_utc).tag(note_tag).do(make_job())


def get_pending_notifications() -> list:
    """Frontend poll hàm này để nhận các thông báo đang chờ."""
    # Luôn trả về nhanh (không hang) — nếu không lấy được lock trong 0.5s
    # thì trả về danh sách rỗng để frontend thử lại sau.
    acquired = _notifications_lock.acquire(timeout=0.5)
    if not acquired:
        return []
    try:
        result = _pending_notifications.copy()
        _pending_notifications.clear()
        return result
    finally:
        _notifications_lock.release()


def reload_all_schedules():
    """Khởi động lại tất cả lịch nhắc từ file (gọi khi server start)."""
    schedule.clear()
    notes = load_all_notes()
    for note in notes:
        if not note.get("done", False):
            schedule_note(note)
    print(f"Loaded {len(notes)} reminder(s) from disk")