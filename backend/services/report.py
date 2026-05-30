import os
import datetime
import re
import datetime
from config import REPORT_FORM_DIR
from services.onedrive import list_files_from_url, download_file, upload_file, delete_file_by_path
from services.metadata import load_metadata
from services.admin import load_sites_config


def get_report_files_for_site(site_key: str) -> dict:
    """
    Trả về dict {label: file_id} cho một site.
    site_key: "ANVL", "ATQB", "ABDNC", "AVG", "AMDR", "LACASTA"
    """
    metadata    = load_metadata()
    onedrive_path = None
    sites_config, _ = load_sites_config()

    for group_sites in sites_config.values():
        if site_key in group_sites:
            onedrive_path = group_sites[site_key]
            break

    if not onedrive_path:
        return {}

    files = list_files_from_url(onedrive_path)
    result = {}
    for f in files:
        label = f["name"].replace(".txt", "").replace(".TXT", "")
        result[label] = f["id"]

    return result


def get_report_text(file_id: str, fname: str, is_no_error: bool = False, raw: bool = False) -> str:
    """
    Đọc nội dung file report từ local cache.
    Nếu chưa có thì tải về từ OneDrive trước.
    """
    metadata = load_metadata()

    # Tìm file local từ metadata
    local_path = None
    if file_id in metadata:
        local_path = metadata[file_id].get("local_path")

    # Nếu không có hoặc không tồn tại → tìm trong REPORT_FORM_DIR
    if not local_path or not os.path.exists(local_path):
        candidate = os.path.join(REPORT_FORM_DIR, os.path.basename(fname))
        if os.path.exists(candidate):
            local_path = candidate

    # Vẫn không có → tải về
    if not local_path or not os.path.exists(local_path):
        # Cần file_dict đầy đủ, tạm dùng id + name
        file_dict = {"id": file_id, "name": fname, "downloadUrl": None}
        local_path = download_file(file_dict, save_dir=REPORT_FORM_DIR)

    if not local_path or not os.path.exists(local_path):
        return f"[Lỗi] Không tìm thấy file: {fname}"

    try:
        with open(local_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if raw:
            return content.strip()

        # Replace các placeholder thời gian bằng giá trị thực tế
        # Dùng UTC+7 (Asia/Ho_Chi_Minh) vì server Docker chạy UTC
        # Replace các placeholder thời gian bằng giá trị thực tế
        # Dùng UTC+7 (Asia/Ho_Chi_Minh) vì server Docker chạy UTC
        now        = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
        time_str   = now.strftime("%H:%M:%S")          # VD: 13:39:05
        date_str   = now.strftime("%d/%m/%Y")          # VD: 19/03/2026
        dt_str     = now.strftime("%H:%M:%S %d/%m/%Y") # VD: 13:39:05 19/03/2026

        yesterday = now - datetime.timedelta(days=1)
        yesterday_str = yesterday.strftime("%d/%m/%Y")

        # Fix cho AEON Văn Giang (và các site có lỗi tương tự) khi dùng "Trong ngày [time]" thay vì "[no_error_time]"
        content = re.sub(r'(Trong ngày\s*)\[time\]', r'\g<1>' + yesterday_str, content, flags=re.IGNORECASE)

        # Fallback lại format cũ: [time] thường -> dt_str (cả ngày lẫn giờ), [Time] in hoa -> time_str (chỉ giờ)
        content = content.replace("[time]",     dt_str)
        content = content.replace("[date]",     date_str)
        content = content.replace("[datetime]", dt_str)
        
        content = re.sub(r'\[no_error_time\]', yesterday_str, content, flags=re.IGNORECASE)
        
        content = content.replace("[Time]",     time_str)
        content = content.replace("[Date]",     date_str)

        return content.strip()
    except Exception as e:
        return f"[Lỗi đọc file] {e}"


def fill_contact_template(template_content: str, dept: str, device: str,
                           status: str, desc: str) -> str:
    """Fill template biểu mẫu Contact."""
    lines = template_content.splitlines()
    result = []
    for line in lines:
        orig = line
        line = line.replace("[title]", dept)
        line = line.replace("[device]", device)
        line = line.replace("[status]", status)
        line = line.replace("[description]", desc)

        stripped = line.strip()
        # Bỏ dòng nếu placeholder chưa được điền và dữ liệu rỗng
        if (("[title]" in orig and not dept) or
                ("[device]" in orig and not device) or
                ("[status]" in orig and not status) or
                ("[description]" in orig and not desc) or
                not stripped):
            continue
        result.append(stripped)

    return "\n".join(result)


def fill_status_template(template_content: str, dept: str, device: str,
                          status: str, time_process: str, desc: str) -> str:
    """Fill template biểu mẫu Status."""
    lines = template_content.splitlines()
    result = []
    for line in lines:
        orig = line
        line = line.replace("[tilte]", dept)   # giữ lỗi typo như gốc
        line = line.replace("[device]", device)
        line = line.replace("[status]", status)
        line = line.replace("[time_process]", time_process)
        line = line.replace("[description]", desc)

        stripped = line.strip()
        if (("[tilte]" in orig and not dept) or
                ("[device]" in orig and not device) or
                ("[status]" in orig and not status) or
                ("[time_process]" in orig and not time_process) or
                ("[description]" in orig and not desc) or
                not stripped):
            continue
        result.append(stripped)

    return "\n".join(result)


def fill_notification_template(template_content: str, site: str, description: str,
                                start_time: str, start_date: str,
                                end_time: str, end_date: str,
                                devices: str, note: str) -> str:
    """Fill template biểu mẫu Notification."""
    lines = template_content.splitlines()
    result = []
    for line in lines:
        line = line.replace("[site]", site)
        line = line.replace("[description]", description)
        line = line.replace("[start_time]", start_time)
        line = line.replace("[start_date]", start_date)
        line = line.replace("[end_time]", end_time)
        line = line.replace("[end_date]", end_date)
        line = line.replace("[devices]", devices)
        line = line.replace("[note]", note)
        stripped = line.strip()
        if stripped:
            result.append(stripped)

    return "\n".join(result)