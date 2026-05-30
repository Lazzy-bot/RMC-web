import os
import json
import datetime
from config import METADATA_FILE, REPORT_FORM_DIR
from services.onedrive import list_files_from_url, download_file


def load_metadata() -> dict:
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_metadata(data: dict):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sync_files_from_onedrive(subfolder_path: str, save_dir: str = None):
    """
    Sync toàn bộ file từ subfolder_path về local.
    Chỉ tải file nếu chưa có hoặc file trên OneDrive mới hơn.
    """
    if not subfolder_path or not subfolder_path.strip():
        return

    if save_dir is None:
        save_dir = REPORT_FORM_DIR

    files          = list_files_from_url(subfolder_path)
    local_metadata = load_metadata()

    for f in files:
        file_id       = f["id"]
        file_name     = f["name"]
        last_modified = f.get("lastModified", "")
        need_download = False

        if file_id not in local_metadata:
            need_download = True
        else:
            meta          = local_metadata[file_id]
            remote_time   = last_modified
            stored_time   = meta.get("lastModifiedDateTime", "")

            if remote_time != stored_time:
                need_download = True
            else:
                # Kiểm tra file có thật sự tồn tại local không
                local_path = meta.get("local_path", "")
                if not local_path or not os.path.exists(local_path):
                    need_download = True

        if need_download:
            filepath = download_file(f, save_dir=save_dir)
            if filepath:
                local_metadata[file_id] = {
                    "name":                  file_name,
                    "lastModifiedDateTime":  last_modified,
                    "local_path":            filepath,
                }

    save_metadata(local_metadata)
    print(f"OK: Synced [{subfolder_path}] -- {len(files)} files")
