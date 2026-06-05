import os
from flask import Blueprint, jsonify, request
from auth import get_session_user
from services.admin import (
    load_sites_config, save_sites_config,
    load_devices_list, save_devices_list,
    load_pics_list, save_pics_list
)
from services.onedrive import upload_file, delete_file_by_path, list_files_from_url
import threading

admin_mgmt_bp = Blueprint("admin_mgmt", __name__, url_prefix="/api/admin")

def check_admin():
    user = get_session_user()
    if not user or user.get("role") != "admin":
        return False
    return True

# --- Sites Management ---

@admin_mgmt_bp.get("/sites/config")
def get_sites_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    sites_config, site_key_map = load_sites_config()
    return jsonify({
        "sites_config": sites_config,
        "site_key_map": site_key_map
    })

@admin_mgmt_bp.post("/sites/config")
def update_sites_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    
    body = request.json or {}
    sites_config = body.get("sites_config")
    site_key_map = body.get("site_key_map")
    
    if sites_config is None or site_key_map is None:
        return jsonify({"error": "Missing data"}), 400
        
    save_sites_config(sites_config, site_key_map)
    
    # --- Tự động đẩy lên OneDrive (Background) ---
    def bg_sync():
        try:
            import json
            from services.onedrive import upload_file
            config_data = json.dumps({"SITES_CONFIG": sites_config, "SITE_KEY_MAP": site_key_map}, ensure_ascii=False, indent=2)
            upload_file("METADATA", "sites_v2.json", config_data)
            print("OK: Synced sites_v2.json to OneDrive (Background)")
        except Exception as e:
            print(f"WARN: Cannot sync sites_v2.json to OneDrive: {e}")
            
    threading.Thread(target=bg_sync).start()
        
    return jsonify({"success": True})

# --- Common Devices Management ---

@admin_mgmt_bp.get("/devices")
def get_devices_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(load_devices_list())

@admin_mgmt_bp.post("/devices")
def update_devices_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    
    devices = request.json
    if not isinstance(devices, list):
        return jsonify({"error": "Data must be a list"}), 400
        
    save_devices_list(devices)
    
    # --- Tự động đẩy lên OneDrive (Background) ---
    def bg_sync():
        try:
            import json
            from services.onedrive import upload_file
            devices_data = json.dumps(devices, ensure_ascii=False, indent=2)
            upload_file("METADATA", "devices.json", devices_data)
            print("OK: Synced devices.json to OneDrive (Background)")
        except Exception as e:
            print(f"WARN: Cannot sync devices.json to OneDrive: {e}")
            
    threading.Thread(target=bg_sync).start()
        
    return jsonify({"success": True})
    
# --- PICs Management ---

@admin_mgmt_bp.get("/pics")
def get_pics_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    return jsonify(load_pics_list())

@admin_mgmt_bp.post("/pics")
def update_pics_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    
    pics = request.json
    if not isinstance(pics, list):
        return jsonify({"error": "Data must be a list"}), 400
        
    save_pics_list(pics)
    
    # --- Tự động đẩy lên OneDrive (Background) ---
    def bg_sync():
        try:
            import json
            from services.onedrive import upload_file
            pics_data = json.dumps(pics, ensure_ascii=False, indent=2)
            upload_file("METADATA", "pics.json", pics_data)
            print("OK: Synced pics.json to OneDrive (Background)")
        except Exception as e:
            print(f"WARN: Cannot sync pics.json to OneDrive: {e}")
            
    threading.Thread(target=bg_sync).start()
        
    return jsonify({"success": True})

# --- Site Items (Templates) Management ---

@admin_mgmt_bp.post("/site-items")
def create_site_item():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    
    body = request.json or {}
    site_key = body.get("site_key")
    filename = body.get("filename")
    content = body.get("content", "")
    
    if not site_key or not filename:
        return jsonify({"error": "Missing site_key or filename"}), 400
        
    if not filename.endswith(".txt"):
        filename += ".txt"
        
    # Find onedrive path
    sites_config, _ = load_sites_config()
    onedrive_path = None
    for group in sites_config.values():
        if site_key in group:
            onedrive_path = group[site_key]
            break
            
    if not onedrive_path:
        return jsonify({"error": f"Site {site_key} not found or has no OneDrive path"}), 404
        
    try:
        success = upload_file(onedrive_path, filename, content)
        if success:
            # Xóa cache local để lần sau fetch sẽ tải bản mới từ OneDrive
            from config import REPORT_FORM_DIR
            local_path = os.path.join(REPORT_FORM_DIR, filename)
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception as e:
                    print(f"WARN: Could not remove local cache: {e}")
            return jsonify({"success": True})
        else:
            return jsonify({"error": "Failed to upload to OneDrive. Please check backend logs or your OneDrive permissions."}), 500
    except Exception as e:
        import traceback
        print(f"ERROR: create_site_item ERROR: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@admin_mgmt_bp.delete("/site-items")
def delete_site_item():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    
    body = request.json or {}
    site_key = body.get("site_key")
    filename = body.get("filename")
    
    if not site_key or not filename:
        return jsonify({"error": "Missing site_key or filename"}), 400
        
    sites_config, _ = load_sites_config()
    onedrive_path = None
    for group in sites_config.values():
        if site_key in group:
            onedrive_path = group[site_key]
            break
            
    if not onedrive_path:
        return jsonify({"error": "Site not found"}), 404
        
    success = delete_file_by_path(onedrive_path, filename)
    if success:
        return jsonify({"success": True})
    return jsonify({"error": "Failed to delete from OneDrive"}), 500

@admin_mgmt_bp.patch("/site-items")
def rename_site_item():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
    
    body = request.json or {}
    file_id = body.get("file_id")
    new_name = body.get("new_name")
    
    if not file_id or not new_name:
        return jsonify({"error": "Missing file_id or new_name"}), 400
        
    if not new_name.endswith(".txt"):
        new_name += ".txt"
        
    from auth import graph_session
    import requests
    
    try:
        token = graph_session.ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # We need drive_id to rename by item_id
        from services.onedrive import _resolve_base_share_link
        drive_id, _ = _resolve_base_share_link()
        
        if not drive_id:
            return jsonify({"error": "Could not resolve OneDrive drive ID"}), 500
            
        api_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}"
        r = requests.patch(api_url, headers=headers, json={"name": new_name}, timeout=10)
        
        if r.status_code == 200:
            return jsonify({"success": True})
        else:
            return jsonify({"error": f"OneDrive error {r.status_code}: {r.text}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@admin_mgmt_bp.delete("/sites")
def delete_site_mgmt():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
        
    body = request.json or {}
    group = body.get("group")
    site = body.get("site")
    
    if not group or not site:
        return jsonify({"error": "Missing group or site"}), 400
        
    sites_config, site_key_map = load_sites_config()
    
    if group in sites_config and site in sites_config[group]:
        onedrive_path = sites_config[group][site]
        # 1. Update config first so the user sees it immediately
        del sites_config[group][site]
        
        # Xóa khỏi key map nếu tồn tại
        upper_site = site.upper()
        if upper_site in site_key_map:
            del site_key_map[upper_site]
        
        save_sites_config(sites_config, site_key_map)
        
        # 2. Delete from OneDrive in Background
        def bg_del():
            from services.onedrive import delete_folder_by_path
            delete_folder_by_path(onedrive_path)
            
        threading.Thread(target=bg_del).start()
        
        return jsonify({"success": True})
    
    return jsonify({"error": "Site not found"}), 404


# --- Config Cloud Sync (Manual) ---

@admin_mgmt_bp.post("/config/sync-from-cloud")
def sync_config_from_cloud():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
        
    from services.onedrive import list_files_from_url, download_file
    from config import METADATA_DIR
    import json
    
    try:
        files = list_files_from_url("METADATA")
        synced = []
        
        for f in files:
            if f["name"] in ["sites_v2.json", "devices.json", "pics.json", "users.json"]:
                if f["name"] == "users.json":
                    # Lưu lại token local trước khi download
                    from config import USERS_DB_FILE
                    import os, json
                    local_tokens = {}
                    if os.path.exists(USERS_DB_FILE):
                        try:
                            with open(USERS_DB_FILE, "r", encoding="utf-8") as file:
                                old_data = json.load(file)
                                for u in old_data.get("users", []):
                                    if u.get("ms_refresh_token"):
                                        local_tokens[u.get("id")] = u.get("ms_refresh_token")
                        except: pass
                        
                    local_path = download_file(f, save_dir=METADATA_DIR, force=True)
                    
                    # Phục hồi token local vào file vừa download
                    if local_path and os.path.exists(local_path):
                        try:
                            with open(local_path, "r", encoding="utf-8") as file:
                                new_data = json.load(file)
                            for u in new_data.get("users", []):
                                uid = u.get("id")
                                if uid in local_tokens:
                                    u["ms_refresh_token"] = local_tokens[uid]
                            with open(local_path, "w", encoding="utf-8") as file:
                                json.dump(new_data, file, ensure_ascii=False, indent=2)
                        except: pass
                    if local_path:
                        synced.append(f["name"])
                else:
                    local_path = download_file(f, save_dir=METADATA_DIR, force=True)
                    if local_path:
                        synced.append(f["name"])
        
        if not synced:
            return jsonify({"error": "Không tìm thấy file cấu hình trên OneDrive (thư mục METADATA)"}), 404
            
        return jsonify({"success": True, "synced": synced})
    except Exception as e:
        return jsonify({"error": f"Lỗi đồng bộ: {str(e)}"}), 500


@admin_mgmt_bp.post("/config/push-to-cloud")
def push_config_to_cloud():
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403
        
    from services.onedrive import upload_file
    from services.admin import load_sites_config, load_devices_list
    import json
    
    try:
        sites_config, site_key_map = load_sites_config()
        devices = load_devices_list()
        
        def bg_push():
            try:
                # Upload sites
                sites_data = json.dumps({"SITES_CONFIG": sites_config, "SITE_KEY_MAP": site_key_map}, ensure_ascii=False, indent=2)
                upload_file("METADATA", "sites_v2.json", sites_data)
                
                # Upload devices
                d_data = json.dumps(devices, ensure_ascii=False, indent=2)
                upload_file("METADATA", "devices.json", d_data)

                # Upload PICs
                pics = load_pics_list()
                p_data = json.dumps(pics, ensure_ascii=False, indent=2)
                upload_file("METADATA", "pics.json", p_data)

                # Upload users.json nhưng bỏ đi ms_refresh_token
                from config import USERS_DB_FILE
                import os, copy
                if os.path.exists(USERS_DB_FILE):
                    try:
                        with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                            users_data = json.load(f)
                        users_data_clean = copy.deepcopy(users_data)
                        for u in users_data_clean.get("users", []):
                            u.pop("ms_refresh_token", None)
                        upload_file("METADATA", "users.json", json.dumps(users_data_clean, ensure_ascii=False, indent=2))
                    except: pass
            except Exception as e:
                print(f"Error in bg_push: {e}")
                
        threading.Thread(target=bg_push).start()


        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Lỗi upload: {str(e)}"}), 500


# ---------------------------------------------------------------------------
# Rate Limiting — Monitor & Control
# ---------------------------------------------------------------------------

@admin_mgmt_bp.get("/rate-limit/stats")
def get_rate_limit_stats():
    """
    Trả về thống kê rate limiting hiện tại của tất cả limiters.
    Chỉ admin được phép truy cập.
    """
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403

    from rate_limiter import ALL_LIMITERS
    from config import RATE_LIMIT_ENABLED

    stats = {
        "enabled": RATE_LIMIT_ENABLED,
        "limiters": [lim.get_stats() for lim in ALL_LIMITERS],
    }
    return jsonify(stats)


@admin_mgmt_bp.post("/rate-limit/reset")
def reset_rate_limit():
    """
    Reset rate limit counter cho một IP hoặc user cụ thể.
    Body: { "key": "192.168.1.1", "limiter": "login" }
    Nếu không truyền "limiter", reset tất cả limiters cho key đó.

    Dùng khi:
    - User bị block nhầm (false positive)
    - Cần unblock IP sau khi kiểm tra
    """
    if not check_admin():
        return jsonify({"error": "Unauthorized"}), 403

    body    = request.json or {}
    key     = body.get("key", "").strip()
    limiter_name = body.get("limiter", "").strip().lower()

    if not key:
        return jsonify({"error": "Missing 'key' (IP address or user email)"}), 400

    from rate_limiter import ALL_LIMITERS

    reset_count = 0
    for lim in ALL_LIMITERS:
        if not limiter_name or lim.name == limiter_name:
            lim.reset_key(key)
            reset_count += 1

    return jsonify({
        "success": True,
        "key": key,
        "limiters_reset": reset_count,
        "message": f"Đã reset {reset_count} limiter(s) cho '{key}'",
    })
