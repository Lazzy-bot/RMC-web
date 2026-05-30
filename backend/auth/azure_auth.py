import os
import time
import json
import threading
import msal
from config import CLIENT_ID, TENANT_ID, AUTHORITY, GRAPH_SCOPES, AZURE_CLIENT_SECRET, METADATA_DIR
import requests

CACHE_FILE = os.path.join(METADATA_DIR, "onedrive_token_cache.bin")
MANUAL_TOKEN_FILE = os.path.join(METADATA_DIR, "onedrive_token_manual.json")


class GraphSession:
    """
    Quản lý phiên Azure AD.
    Hỗ trợ device flow (không cần browser popup như Tkinter).
    Frontend sẽ poll /api/auth/status để biết khi nào login xong.
    """

    def __init__(self):
        self.cache = msal.SerializableTokenCache()
        if os.path.exists(CACHE_FILE):
            try:
                self.cache.deserialize(open(CACHE_FILE, "r").read())
            except Exception as e:
                print(f"WARN: Error deserializing MSAL cache: {e}")

        self.app = msal.PublicClientApplication(
            CLIENT_ID, authority=AUTHORITY, token_cache=self.cache
        )
        self.account  = None
        self.token    = None

        # Load manual token from persistent file if exists (for AZURE_CLIENT_SECRET manual flow)
        if os.path.exists(MANUAL_TOKEN_FILE):
            try:
                with open(MANUAL_TOKEN_FILE, "r") as f:
                    self.token = json.load(f)
                print("INFO: Loaded manual token from cache successfully!")
            except Exception as e:
                print(f"WARN: Error loading manual token cache: {e}")

        # Device flow state (dùng cho frontend polling)
        self._flow             = None
        self._flow_result      = None
        self._flow_in_progress = False
        self._flow_lock        = threading.Lock()

    # ------------------------------------------------------------------
    def save_cache(self):
        if self.cache.has_state_changed:
            try:
                with open(CACHE_FILE, "w") as f:
                    f.write(self.cache.serialize())
            except Exception as e:
                print(f"WARN: Error writing MSAL cache: {e}")
        
        # Luôn persistent lưu self.token thủ công (chứa refresh_token cho silent refresh)
        if self.token:
            try:
                with open(MANUAL_TOKEN_FILE, "w") as f:
                    json.dump(self.token, f)
            except Exception as e:
                print(f"WARN: Error writing manual token cache: {e}")

    # ------------------------------------------------------------------
    def refresh_token_manually(self):
        """Làm mới token bằng refresh_token thủ công (cho flow client_secret)."""
        if not self.token or "refresh_token" not in self.token:
            return None

        token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        
        # 1. Thử làm mới không dùng client_secret trước (phù hợp cho Public Client)
        data = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": self.token["refresh_token"],
            "scope": " ".join(GRAPH_SCOPES) + " offline_access"
        }

        try:
            print("INFO: Trying to refresh token without client_secret...")
            r = requests.post(token_url, data=data, timeout=10)
            rj = r.json()
            
            # Nếu thất bại do thiếu client_secret (App là Confidential Client) 
            # hoặc gặp mã lỗi AADSTS7000218 / invalid_client, ta sẽ thử lại với client_secret
            is_secret_required = False
            if r.status_code != 200:
                err_desc = rj.get("error_description", "")
                err_code = rj.get("error", "")
                if "client_secret" in err_desc or "AADSTS7000218" in err_desc or err_code == "invalid_client":
                    is_secret_required = True

            if r.status_code != 200 and AZURE_CLIENT_SECRET and is_secret_required:
                print("INFO: Detected client_secret required. Retrying with client_secret...")
                data_with_secret = data.copy()
                data_with_secret["client_secret"] = AZURE_CLIENT_SECRET
                r = requests.post(token_url, data=data_with_secret, timeout=10)
                rj = r.json()

            if "access_token" in rj:
                print("INFO: Silent refresh of manual token succeeded!")
                # Gán scopes trả về bằng GRAPH_SCOPES nếu thiếu
                if "scope" not in rj:
                    rj["scope"] = self.token.get("scope") or " ".join(GRAPH_SCOPES)
                if "expires_in" in rj:
                    rj["expires_on"] = int(time.time()) + int(rj["expires_in"])
                # Giữ lại refresh_token cũ nếu response mới không trả về refresh_token mới
                if "refresh_token" not in rj:
                    rj["refresh_token"] = self.token["refresh_token"]
                
                self.token = rj
                self.save_cache()
                return rj["access_token"]
            else:
                err = rj.get("error_description") or rj.get("error") or "Không rõ nguyên nhân"
                print(f"ERROR: Manual token refresh error: {err}")
        except Exception as e:
            print(f"ERROR: Exception during manual token refresh: {e}")

        return None


    # ------------------------------------------------------------------
    def get_valid_token(self):
        """Trả về access_token hợp lệ. Nếu hết hạn thì silent refresh."""
        # 1. Kiểm tra xem token trong bộ nhớ có hợp lệ không
        if self.token and "access_token" in self.token:
            expires_at = self.token.get("expires_on")
            if expires_at and int(expires_at) > int(time.time()) + 60:
                return self.token["access_token"]

        # 2. Nếu hết hạn hoặc thiếu expires_on, thử refresh thủ công bằng refresh_token
        if self.token and "refresh_token" in self.token:
            print("INFO: Detected expired or unknown token expiry. Performing silent refresh...")
            refreshed = self.refresh_token_manually()
            if refreshed:
                return refreshed

        # 3. Thử silent refresh bằng MSAL (cho flow Public Client / không secret)
        accounts = self.app.get_accounts()
        if accounts:
            self.account = accounts[0]
            try:
                self.token = self.app.acquire_token_silent(GRAPH_SCOPES, account=self.account)
            except Exception as e:
                print(f"WARN: MSAL silent refresh failed: {e}")

        # 4. Kiểm tra lại token sau khi dùng MSAL silent refresh
        if self.token and "access_token" in self.token:
            expires_at = self.token.get("expires_on")
            if not expires_at and "expires_in" in self.token:
                self.token["expires_on"] = int(time.time()) + int(self.token["expires_in"])
                expires_at = self.token["expires_on"]

            if expires_at and int(expires_at) > int(time.time()) + 60:
                self.save_cache()
                return self.token["access_token"]

        # 5. Nếu tất cả đều thất bại và token cũ hết hạn thực sự, trả về None (yêu cầu đăng nhập lại)
        print("ERROR: No valid token found and automatic refresh failed.")
        return None

    # ------------------------------------------------------------------
    def start_device_flow(self):
        """
        Khởi động device flow. Trả về dict gồm:
          - user_code, verification_uri  (hiển thị lên frontend)
          - status: "pending"
        """
        with self._flow_lock:
            if self._flow_in_progress:
                return self._get_flow_status()

            flow = self.app.initiate_device_flow(scopes=GRAPH_SCOPES)
            if "user_code" not in flow:
                err_msg = flow.get("error_description") or flow.get("error") or "Không xác định"
                raise Exception(f"Lỗi khởi tạo Device Flow: {err_msg}")

            self._flow             = flow
            self._flow_result      = None
            self._flow_in_progress = True

        # Chạy background thread chờ user login
        threading.Thread(target=self._wait_for_device_login, daemon=True).start()

        return {
            "status":           "pending",
            "user_code":        flow["user_code"],
            "verification_uri": flow["verification_uri"],
        }

    def _wait_for_device_login(self):
        if AZURE_CLIENT_SECRET:
            # Dùng requests poll thủ công để có thể gắn client_secret nếu cần
            token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
            data = {
                "client_id": CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": self._flow["device_code"]
            }
            expires_at = time.time() + self._flow.get("expires_in", 900)
            interval = self._flow.get("interval", 5)
            result = None
            use_secret = False

            # Tự động dò xem client có yêu cầu secret không bằng cách gửi thử không secret lần đầu
            try:
                r_detect = requests.post(token_url, data=data, timeout=10)
                rj_detect = r_detect.json()
                if r_detect.status_code != 200:
                    err_desc = rj_detect.get("error_description", "")
                    err_code = rj_detect.get("error", "")
                    if "client_secret" in err_desc or "AADSTS7000218" in err_desc or err_code == "invalid_client":
                        use_secret = True
                        print("INFO: Device identified as Confidential Client, will use client_secret for polling.")
            except Exception as e:
                print(f"WARN: Error during automatic client type detection: {e}")

            while time.time() < expires_at:
                poll_data = data.copy()
                if use_secret and AZURE_CLIENT_SECRET:
                    poll_data["client_secret"] = AZURE_CLIENT_SECRET

                r = requests.post(token_url, data=poll_data, timeout=10)
                rj = r.json()
                if "error" in rj:
                    if rj["error"] == "authorization_pending":
                        time.sleep(interval)
                        continue
                    else:
                        result = rj
                        break
                else:
                    # Gán scopes trả về bằng GRAPH_SCOPES nếu thiếu
                    if "scope" not in rj:
                        rj["scope"] = " ".join(GRAPH_SCOPES)
                    if "expires_in" in rj:
                        rj["expires_on"] = int(time.time()) + int(rj["expires_in"])
                    result = rj
                    break
        else:
            # Flow mặc định bằng MSAL (chỉ dùng được cho App bật "Allow public client flows = Yes")
            result = self.app.acquire_token_by_device_flow(self._flow)


        with self._flow_lock:
            self._flow_result      = result
            self._flow_in_progress = False
            if result and "access_token" in result:
                self.token = result
                self.save_cache()

    def _get_flow_status(self):
        flow = self._flow
        return {
            "status":           "pending",
            "user_code":        flow["user_code"] if flow else "",
            "verification_uri": flow["verification_uri"] if flow else "",
        }

    # ------------------------------------------------------------------
    def check_device_flow_result(self):
        """
        Frontend gọi hàm này để poll trạng thái login.
        Returns:
            {"status": "pending"}
            {"status": "success"}
            {"status": "error", "message": "..."}
        """
        with self._flow_lock:
            if self._flow_in_progress:
                return {"status": "pending"}
            if self._flow_result is None:
                return {"status": "idle"}
            result = self._flow_result

        if "access_token" in result:
            return {"status": "success"}
        else:
            err = result.get("error_description") or result.get("error") or "Login thất bại"
            return {"status": "error", "error": err, "message": err}

    # ------------------------------------------------------------------
    def ensure_token(self):
        """
        Đảm bảo luôn có token hợp lệ.
        Raise Exception nếu chưa login.
        """
        token = self.get_valid_token()
        if not token:
            raise Exception("Chưa đăng nhập. Vui lòng đăng nhập qua /api/auth/device-flow")
        return token

    # ------------------------------------------------------------------
    def refresh_in_background(self):
        """Gọi khi token sắp hết hạn — không block caller."""
        def _do_refresh():
            try:
                self.get_valid_token()
            except Exception as e:
                print(f"WARN background refresh: {e}")
        threading.Thread(target=_do_refresh, daemon=True).start()

    # ------------------------------------------------------------------
    @property
    def is_authenticated(self) -> bool:
        """Chỉ check cache local — KHÔNG gọi network."""
        if not self.token or "access_token" not in self.token:
            return False
        expires_at = self.token.get("expires_on")
        if not expires_at:
            return True  # Không biết hạn → coi như còn hạn
        remaining = int(expires_at) - int(time.time())
        # Sắp hết hạn trong 5 phút → refresh ngầm, không block
        if remaining < 300:
            self.refresh_in_background()
        return remaining > 60


# Singleton instance
graph_session = GraphSession()
