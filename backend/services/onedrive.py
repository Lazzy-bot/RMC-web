import os
import base64
import datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from auth import graph_session
from config import BASE_SHARE_LINK, REPORT_FORM_DIR

# Session dùng chung với connection pool và retry strategy
# Tự động retry khi gặp lỗi mạng tạm thời (500, 502, 503, 504)
_session = requests.Session()
_retry = Retry(
    total=2,                    # Tối đa 2 lần retry
    backoff_factor=0.3,         # Chờ 0.3s giữa các lần retry
    status_forcelist=[500, 502, 503, 504],
    raise_on_status=False,
)
_session.mount("https://", HTTPAdapter(max_retries=_retry, pool_connections=10, pool_maxsize=20))

# Cache driveId và rootItemId để không gọi lại mỗi lần
_drive_cache = {"drive_id": None, "root_item_id": None}


def _resolve_base_share_link():
    """Lấy driveId và itemId của folder ROOT từ BASE_SHARE_LINK."""
    if _drive_cache["drive_id"] and _drive_cache["root_item_id"]:
        return _drive_cache["drive_id"], _drive_cache["root_item_id"]

    token   = graph_session.ensure_token()
    headers = {"Authorization": f"Bearer {token}"}

    link = BASE_SHARE_LINK.strip().split("?")[0]
    encoded = base64.b64encode(link.encode("utf-8")).decode("utf-8")
    encoded = encoded.rstrip("=").replace("/", "_").replace("+", "-")

    r = _session.get(
        f"https://graph.microsoft.com/v1.0/shares/u!{encoded}/driveItem",
        headers=headers,
        timeout=15
    )

    if r.status_code != 200:
        error_data = {}
        try:
            error_data = r.json()
        except:
            pass
        msg = error_data.get("error", {}).get("message") or r.text
        print(f"ERROR: Cannot resolve BASE_SHARE_LINK: {r.status_code} | msg: {msg}")
        raise Exception(f"Không thể truy cập link SharePoint (Error {r.status_code}): {msg}")

    data          = r.json()
    drive_id      = data["parentReference"]["driveId"]
    root_item_id  = data["id"]

    _drive_cache["drive_id"]     = drive_id
    _drive_cache["root_item_id"] = root_item_id
    return drive_id, root_item_id


def list_files_from_url(subfolder_path: str) -> list:
    """
    Lấy danh sách file trong subfolder của OneDrive.
    subfolder_path: đường dẫn tương đối từ ROOT, vd "REPORT FORM/NVL REPORT FORM"
    """
    if not subfolder_path or not subfolder_path.strip():
        return []

    token   = graph_session.ensure_token()
    headers = {"Authorization": f"Bearer {token}"}

    drive_id, root_item_id = _resolve_base_share_link()
    if not drive_id:
        return []

    api_url = (
        f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
        f"/items/{root_item_id}:/{subfolder_path}:/children"
    )

    r = _session.get(api_url, headers=headers, timeout=15)

    if r.status_code == 200:
        items = r.json().get("value", [])
        return [
            {
                "id":           item["id"],
                "name":         item["name"],
                "downloadUrl":  item.get("@microsoft.graph.downloadUrl"),
                "lastModified": item.get("lastModifiedDateTime"),
            }
            for item in items if "file" in item
        ]
    else:
        error_data = {}
        try:
            error_data = r.json()
        except:
            pass
        msg = error_data.get("error", {}).get("message") or r.text
        print(f"ERROR: API ERROR {r.status_code} | path: {subfolder_path} | msg: {msg}")
        raise Exception(f"OneDrive API Error {r.status_code}: {msg}")


def download_file(file_dict: dict, save_dir: str = None, force: bool = False) -> str | None:
    """
    Tải file từ OneDrive về local.
    file_dict: {"id", "name", "downloadUrl", "lastModified"}
    save_dir: thư mục đích (mặc định REPORT_FORM_DIR)
    force: bỏ qua kiểm tra thời gian local để ghi đè
    Returns: local path hoặc None nếu lỗi.
    """
    try:
        if save_dir is None:
            save_dir = REPORT_FORM_DIR
        os.makedirs(save_dir, exist_ok=True)

        fname        = os.path.basename(file_dict["name"])
        download_url = file_dict.get("downloadUrl")
        remote_time  = file_dict.get("lastModified")

        if not download_url:
            # Lấy lại downloadUrl qua Graph API
            token   = graph_session.ensure_token()
            headers = {"Authorization": f"Bearer {token}"}
            drive_id, _ = _resolve_base_share_link()
            meta = requests.get(
                f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_dict['id']}",
                headers=headers,
                timeout=15
            ).json()
            download_url = meta.get("@microsoft.graph.downloadUrl")
            remote_time  = meta.get("lastModifiedDateTime")

        if not download_url:
            return None

        path = os.path.join(save_dir, fname)

        # Skip nếu file local vẫn còn mới hơn
        if not force and os.path.exists(path) and remote_time:
            local_time = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            remote_dt  = datetime.datetime.fromisoformat(
                remote_time.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            if local_time >= remote_dt:
                return path

        r = requests.get(download_url, stream=True, timeout=15)
        if r.status_code == 200:
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return path
        return None

    except Exception as e:
        print(f"ERROR: download_file ERROR: {e}")
        return None


def upload_file(subfolder_path: str, filename: str, content: str) -> bool:
    """
    Tạo hoặc cập nhật file trên OneDrive.
    """
    try:
        token = graph_session.ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain; charset=utf-8"
        }
        drive_id, root_item_id = _resolve_base_share_link()
        if not drive_id:
            return False

        from urllib.parse import quote
        path_clean = subfolder_path.strip("/")
        quoted_path = quote(path_clean)
        quoted_name = quote(filename.strip("/"))
        
        # Ensure parent folder exists
        if path_clean:
            # Check if folder exists
            check_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{root_item_id}:/{quoted_path}"
            r_check = requests.get(check_url, headers={"Authorization": f"Bearer {token}"}, timeout=8)
            if r_check.status_code == 404:
                # Create folder
                print(f"INFO: Folder {path_clean} not found, creating...")
                create_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{root_item_id}/children"
                create_data = {
                    "name": path_clean,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "replace"
                }
                r_create = requests.post(create_url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=create_data, timeout=8)
                if not r_create.ok:
                    print(f"ERROR: Failed to create folder: {r_create.text}")

        # PUT /drives/{drive-id}/items/{parent-id}:/{filename}:/content
        api_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/items/{root_item_id}:/{quoted_path}/{quoted_name}:/content"
        )

        r = requests.put(api_url, headers=headers, data=content.encode("utf-8"), timeout=15)
        if r.status_code in [200, 201]:
            print(f"OK: Uploaded {filename} to {subfolder_path}")
            return True
        else:
            print(f"ERROR: Upload ERROR {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"ERROR: upload_file ERROR: {e}")
        return False


def delete_file_by_path(subfolder_path: str, filename: str) -> bool:
    """
    Xóa file trên OneDrive theo đường dẫn.
    """
    try:
        token = graph_session.ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        drive_id, root_item_id = _resolve_base_share_link()
        if not drive_id:
            return False

        from urllib.parse import quote
        quoted_path = quote(subfolder_path.strip("/"), safe="/")
        quoted_name = quote(filename.strip("/"), safe="/")
        
        api_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/items/{root_item_id}:/{quoted_path}/{quoted_name}"
        )

        r = requests.delete(api_url, headers=headers, timeout=15)
        if r.status_code == 204:
            print(f"OK: Deleted {filename} from {subfolder_path}")
            return True
        else:
            print(f"ERROR: Delete ERROR {r.status_code}: {r.text}")
            return False
    except Exception as e:
        print(f"ERROR: delete_file ERROR: {e}")
        return False


def delete_folder_by_path(folder_path: str) -> bool:
    """
    Xóa hoàn toàn một thư mục trên OneDrive.
    """
    try:
        token = graph_session.ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        drive_id, root_item_id = _resolve_base_share_link()
        if not drive_id:
            print("ERROR: delete_folder ERROR: No drive_id found")
            return False

        from urllib.parse import quote
        quoted_path = quote(folder_path.strip("/"), safe="/")
        
        # Try path-based delete first
        api_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/items/{root_item_id}:/{quoted_path}"
        )
        
        print(f"DEBUG: Deleting folder by path: {api_url}")
        r = requests.delete(api_url, headers=headers, timeout=15)
        
        if r.status_code == 204:
            print(f"OK: Deleted folder (path): {folder_path}")
            return True
            
        # If 404, maybe it's already gone or path is weird. Try to resolve ID first
        print(f"WARN: Delete by path failed ({r.status_code}: {r.text}). Trying to resolve ID first...")
        
        # Resolve ID
        get_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{root_item_id}:/{quoted_path}"
        r_get = requests.get(get_url, headers=headers, timeout=15)
        if r_get.status_code == 200:
            item_id = r_get.json().get("id")
            if item_id:
                print(f"DEBUG: Found item ID {item_id} for path {folder_path}. Deleting by ID...")
                del_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}"
                r_del = requests.delete(del_url, headers=headers, timeout=15)
                if r_del.status_code == 204:
                    print(f"OK: Deleted folder (ID): {folder_path}")
                    return True
                else:
                    print(f"ERROR: Delete by ID failed: {r_del.status_code} | {r_del.text}")
        else:
            print(f"ERROR: Could not resolve path to ID: {r_get.status_code} | {r_get.text}")

        print(f"ERROR: delete_folder final failure for: {folder_path}")
        return False
    except Exception as e:
        import traceback
        print(f"ERROR: delete_folder EXCEPTION: {e}")
        traceback.print_exc()
        return False
