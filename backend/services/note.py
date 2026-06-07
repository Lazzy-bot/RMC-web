import os
import json
import datetime
import threading
import schedule
import time
from config import NOTE_ARCHIVE_DIR

# Danh sách các reminder đang hoạt động (pending notifications) theo từng user email
_pending_notifications = {}
_notifications_lock    = threading.Lock()
_schedule_lock         = threading.RLock()

# Schedule runner
_schedule_thread_started = False


def _start_schedule_runner():
    global _schedule_thread_started
    if _schedule_thread_started:
        return
    _schedule_thread_started = True

    def run():
        while True:
            with _schedule_lock:
                try:
                    schedule.run_pending()
                except Exception as e:
                    print(f"ERROR running pending schedules: {e}")
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
    with _schedule_lock:
        try:
            schedule.clear(tag)
        except Exception as e:
            print(f"ERROR clearing schedules for tag {tag}: {e}")


def _purge_pending_notifications(tag: str) -> None:
    with _notifications_lock:
        for email in list(_pending_notifications.keys()):
            _pending_notifications[email] = [
                item for item in _pending_notifications[email]
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

    try:
        filenames = os.listdir(NOTE_ARCHIVE_DIR)
    except Exception as e:
        print(f"ERROR listing directory {NOTE_ARCHIVE_DIR}: {e}")
        return result

    for fname in sorted(filenames):
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
                if "paused" not in data:
                    data["paused"] = False
                if "repeat_count" not in data:
                    data["repeat_count"] = 1
                if "repeat_interval" not in data:
                    data["repeat_interval"] = 5
                if "emails" not in data:
                    data["emails"] = []
                if "scheduled_at" not in data:
                    try:
                        mtime = os.path.getmtime(fpath)
                        data["scheduled_at"] = datetime.datetime.fromtimestamp(mtime).isoformat()
                    except Exception:
                        data["scheduled_at"] = datetime.datetime.now().isoformat()
                result.append(data)
        except Exception as e:
            print(f"ERROR reading {fname}: {e}")

    result.sort(key=lambda d: d.get("_stt", 0))
    return result


def create_note(keyword: str, content: str, times: list, days: list,
                months: list, mode: str, delete_mode: str = "delete",
                repeat_count: int = 1, repeat_interval: int = 5,
                emails: list = None, ms_token: str = None,
                creator_email: str = None) -> dict:
    """Tạo note mới, lưu file JSON, và lên lịch."""
    stt   = _get_next_stt()
    fpath = os.path.join(NOTE_ARCHIVE_DIR, f"reminders{stt}.json")

    data = {
        "keyword":         keyword,
        "content":         content,
        "times":           times,
        "days":            days,
        "months":          months,
        "mode":            mode,
        "delete_mode":     delete_mode,
        "repeat_count":    int(repeat_count),
        "repeat_interval": int(repeat_interval),
        "emails":          emails or [],
        "paused":          False,
        "done":            False,
        "creator_email":   creator_email,
        "scheduled_at":    datetime.datetime.now().isoformat(),
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    data["_file"] = fpath
    data["_stt"]  = stt
    data["_tag"]  = _note_tag(stt=stt)

    schedule_note(data)

    if data.get("emails"):
        try:
            # Lấy refresh_token để dùng khi cần cho scheduler
            ms_refresh_token = None
            sender_email = None
            if ms_token:
                # Cố gắng lấy refresh_token từ users.json để lưu vào note nếu cần
                try:
                    from auth.user_auth import get_ms_refresh_token_by_email
                    # Tìm email người tạo (sẽ là email trong emails đầu tiên nếu user tự thêm mình)
                except Exception:
                    pass
        except Exception as e:
            print(f"ERROR: process CREATE emails failed: {e}")

    return data


def update_note(stt: int, keyword: str, content: str, times: list, days: list,
                months: list, mode: str, delete_mode: str = "delete",
                repeat_count: int = 1, repeat_interval: int = 5,
                emails: list = None, paused: bool = False,
                ms_token: str = None, creator_email: str = None) -> dict:
    """Cập nhật thông tin note, ghi lại file JSON, và lên lịch lại."""
    fpath = os.path.join(NOTE_ARCHIVE_DIR, f"reminders{stt}.json")
    if not os.path.exists(fpath):
        raise FileNotFoundError(f"Không tìm thấy note {stt}")

    # Đọc dữ liệu cũ
    with open(fpath, "r", encoding="utf-8") as f:
        old_data = json.load(f)
    done = old_data.get("done", False)
    saved_creator = old_data.get("creator_email")

    data = {
        "keyword":         keyword,
        "content":         content,
        "times":           times,
        "days":            days,
        "months":          months,
        "mode":            mode,
        "delete_mode":     delete_mode,
        "repeat_count":    int(repeat_count),
        "repeat_interval": int(repeat_interval),
        "emails":          emails or [],
        "paused":          paused,
        "done":            done,
        "creator_email":   creator_email or saved_creator,
        "scheduled_at":    datetime.datetime.now().isoformat(),
    }

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    data["_file"] = fpath
    data["_stt"]  = stt
    data["_tag"]  = _note_tag(stt=stt)

    # Cancel schedule cũ
    tag = data["_tag"]
    _cancel_note_schedules(tag)
    _purge_pending_notifications(tag)

    # Lên lịch lại nếu chưa xong và không bị pause
    if not done and not paused:
        schedule_note(data)

    return data


def pause_note(stt: int) -> bool:
    """Tạm dừng lịch nhắc của note."""
    fpath = os.path.join(NOTE_ARCHIVE_DIR, f"reminders{stt}.json")
    if not os.path.exists(fpath):
        return False

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["paused"] = True

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    tag = _note_tag(stt=stt)
    _cancel_note_schedules(tag)
    _purge_pending_notifications(tag)
    return True


def resume_note(stt: int) -> bool:
    """Tiếp tục lịch nhắc của note."""
    fpath = os.path.join(NOTE_ARCHIVE_DIR, f"reminders{stt}.json")
    if not os.path.exists(fpath):
        return False

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["paused"] = False
    data["scheduled_at"] = datetime.datetime.now().isoformat()

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    data["_file"] = fpath
    data["_stt"]  = stt
    data["_tag"]  = _note_tag(stt=stt)

    if not data.get("done", False):
        _cancel_note_schedules(data["_tag"])  # Đảm bảo không bị trùng
        schedule_note(data)
    return True


def delete_note(file_path: str, stt: int | None = None, note_tag: str | None = None) -> bool:
    """Xóa file note và hủy toàn bộ lịch liên quan."""
    tag = note_tag or _note_tag(stt=stt)
    try:
        with _schedule_lock:
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


def _is_note_completed(note: dict, now: datetime.datetime) -> bool:
    scheduled_at_str = note.get("scheduled_at")
    if scheduled_at_str:
        try:
            scheduled_at = datetime.datetime.fromisoformat(scheduled_at_str)
        except Exception:
            scheduled_at = now
    else:
        scheduled_at = now

    times = note.get("times", [])
    days = note.get("days", [])
    months = note.get("months", [])

    dts = []
    for m in months:
        for d in days:
            for t in times:
                try:
                    month = int(m)
                    day = int(d)
                    h, min_val = map(int, t.split(":"))
                    dt = datetime.datetime(scheduled_at.year, month, day, h, min_val)
                    if dt < scheduled_at:
                        dt = datetime.datetime(scheduled_at.year + 1, month, day, h, min_val)
                    dts.append(dt)
                except Exception:
                    pass

    if not dts:
        return True

    max_dt = max(dts)
    now_trunc = now.replace(second=0, microsecond=0)
    max_dt_trunc = max_dt.replace(second=0, microsecond=0)
    return now_trunc >= max_dt_trunc


def _handle_completed_note(note: dict) -> None:
    file_path = note.get("_file")
    delete_mode = note.get("delete_mode", "delete")
    note_tag = _note_tag(note)
    
    _cancel_note_schedules(note_tag)
    
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


def schedule_note(note: dict):
    """Lên lịch nhắc cho một note."""
    if note.get("paused", False):
        return

    _start_schedule_runner()

    keyword         = note["keyword"]
    content         = note["content"]
    times           = note["times"]
    days            = note["days"]
    months          = note["months"]
    mode            = note["mode"]
    delete_mode     = note.get("delete_mode", "delete")
    file_path       = note.get("_file")
    note_tag        = _note_tag(note)
    repeat_count    = int(note.get("repeat_count", 1))
    repeat_interval = int(note.get("repeat_interval", 5))
    emails          = note.get("emails", [])

    for t in times:
        def make_job(t=t):
            def job():
                # Kiem tra ngay/thang theo gio Viet Nam
                now = datetime.datetime.now()
                if str(now.day) not in days or str(now.month) not in months:
                    return

                def trigger_notification(time_label):
                    # Đẩy notification vào queue để frontend poll
                    with _notifications_lock:
                        targets = set()
                        if emails:
                            for em in emails:
                                if em:
                                    targets.add(em.strip().lower())
                        c_email = note.get("creator_email")
                        if c_email:
                            targets.add(c_email.strip().lower())
                        
                        # Fallback nếu không có email nhận/creator cụ thể:
                        # Gửi cho tất cả users đã đăng ký trong hệ thống
                        if not targets:
                            try:
                                from auth.user_auth import list_users
                                for u in list_users():
                                    u_email = u.get("email")
                                    if u_email:
                                        targets.add(u_email.strip().lower())
                            except Exception as ex:
                                print(f"[Note Trigger] Error listing users for fallback: {ex}")
                        
                        for target in targets:
                            if target not in _pending_notifications:
                                _pending_notifications[target] = []
                            _pending_notifications[target].append({
                                "keyword": keyword,
                                "content": content,
                                "time":    time_label,
                                "note_tag": note_tag,
                            })

                    # Gửi email nhắc nhở nếu có email và cấu hình SMTP
                    if emails:
                        from services.email_service import send_reminder_email
                        # Lấy refresh_token từ users.json (dùng khi gửi lúc offline/scheduler)
                        ms_refresh = None
                        sender_em = None
                        try:
                            from auth.user_auth import get_ms_refresh_token_by_email, get_any_ms_refresh_token
                            # 1. Tìm token của người tạo ra cái note này
                            c_email = note.get("creator_email")
                            if c_email:
                                ms_refresh = get_ms_refresh_token_by_email(c_email)
                                sender_em = c_email
                            
                            # 2. Nếu không có, tìm token trong danh sách người nhận
                            if not ms_refresh:
                                for candidate_email in emails:
                                    rt = get_ms_refresh_token_by_email(candidate_email)
                                    if rt:
                                        ms_refresh = rt
                                        sender_em = candidate_email
                                        break
                                        
                            # 3. Nếu vẫn không có, lấy bất kỳ token Microsoft nào trong hệ thống làm fallback
                            if not ms_refresh:
                                rt, email_found = get_any_ms_refresh_token()
                                if rt:
                                    ms_refresh = rt
                                    sender_em = email_found
                                    print(f"[Scheduler Email] Fallback sử dụng token của {sender_em} để gửi thay cho {c_email or 'unknown creator'}")
                        except Exception as e:
                            print(f"[Scheduler Email] Lỗi lấy refresh token: {e}")
                            
                        send_reminder_email(keyword, content, time_label, emails,
                                            ms_refresh_token=ms_refresh,
                                            sender_email=sender_em)

                # Trigger lần đầu tiên
                trigger_notification(t)

                # Thiết lập lặp lại (bất đồng bộ qua thread)
                if repeat_count > 1 and repeat_interval > 0:
                    def repeat_runner():
                        for i in range(1, repeat_count):
                            time.sleep(repeat_interval * 60)
                            # Kiểm tra xem lịch có bị hủy hoặc pause giữa chừng hay không
                            with _schedule_lock:
                                has_jobs = bool(schedule.get_jobs(note_tag))
                            if not has_jobs:
                                break
                            try:
                                with open(file_path, "r", encoding="utf-8") as f:
                                    curr_data = json.load(f)
                                if curr_data.get("paused") or curr_data.get("done"):
                                    break
                            except:
                                break

                            # Tính thời gian lặp tiếp theo hiển thị trên email/web
                            try:
                                h, m = map(int, t.split(":"))
                                total_mins = h * 60 + m + (repeat_interval * i)
                                rep_time = f"{(total_mins // 60) % 24:02d}:{total_mins % 60:02d}"
                            except:
                                rep_time = t

                            trigger_notification(rep_time)

                    threading.Thread(target=repeat_runner, daemon=True).start()

                if mode == "1 lần":
                    if _is_note_completed(note, now):
                        _handle_completed_note(note)
                        return schedule.CancelJob

            return job

        with _schedule_lock:
            try:
                schedule.every().day.at(t).tag(note_tag).do(make_job())
            except Exception as e:
                print(f"ERROR scheduling note job at {t}: {e}")


def get_pending_notifications(user_email: str | None = None) -> list:
    """Frontend poll hàm này để nhận các thông báo đang chờ."""
    # Luôn trả về nhanh (không hang) — nếu không lấy được lock trong 0.5s
    # thì trả về danh sách rỗng để frontend thử lại sau.
    if not user_email:
        return []
    acquired = _notifications_lock.acquire(timeout=0.5)
    if not acquired:
        return []
    try:
        email_key = user_email.strip().lower()
        if email_key in _pending_notifications:
            result = _pending_notifications[email_key].copy()
            _pending_notifications[email_key].clear()
            return result
        return []
    finally:
        _notifications_lock.release()


def reload_all_schedules():
    """Khởi động lại tất cả lịch nhắc từ file (gọi khi server start)."""
    try:
        with _schedule_lock:
            schedule.clear()
        notes = load_all_notes()
        for note in notes:
            if not note.get("done", False) and not note.get("paused", False):
                if note.get("mode") == "1 lần" and _is_note_completed(note, datetime.datetime.now()):
                    _handle_completed_note(note)
                else:
                    schedule_note(note)
        print(f"Loaded {len(notes)} reminder(s) from disk")
    except Exception as e:
        print(f"ERROR reloading all schedules: {e}")