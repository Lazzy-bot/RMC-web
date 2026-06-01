import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Application Auth (end-user login)
# ============================================================
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "rmc-assistant-change-me")
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL", "") or "").rstrip("/")

# Hard admin accounts (comma separated list supported).
# Example: ADMIN_EMAILS=dung.ho@aeondelight.biz,admin@company.com
ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
]

# OAuth credentials for end-user sign in
MS_OAUTH_CLIENT_ID = os.getenv("MS_OAUTH_CLIENT_ID", "")
MS_OAUTH_CLIENT_SECRET = os.getenv("MS_OAUTH_CLIENT_SECRET", "")

GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

# ============================================================
# Azure AD Configuration
# ============================================================
CLIENT_ID  = os.getenv("AZURE_CLIENT_ID") or MS_OAUTH_CLIENT_ID or "f65f87c2-73ce-43e7-8576-c83f8733bd1a"
TENANT_ID  = os.getenv("AZURE_TENANT_ID",  "5983a1d2-f46b-492d-a9b3-7e2f3609d20b")
# Nếu dùng CLIENT_ID mặc định của Office, bắt buộc không dùng secret để chạy public client flow
AZURE_CLIENT_SECRET = "" if CLIENT_ID == "ac4edccf-a8ee-41aa-bcc4-6603c4bebae1" else (os.getenv("AZURE_CLIENT_SECRET", "") or MS_OAUTH_CLIENT_SECRET)
MS_OAUTH_TENANT_ID = os.getenv("MS_OAUTH_TENANT_ID") or TENANT_ID
AUTHORITY  = f"https://login.microsoftonline.com/{TENANT_ID}"
GRAPH_SCOPES = ["Files.Read", "Files.ReadWrite"]

# ============================================================
# Base OneDrive share link (ROOT folder)
# ============================================================
BASE_SHARE_LINK = os.getenv(
    "BASE_SHARE_LINK",
    "https://aeondelight-my.sharepoint.com/:f:/g/personal/giap_dinh_aeondelight_biz/IgDS8nHHoSyATLdDJeXhmPueAY1REBfxUKVzI3BFLLsYRGQ"
)

# ============================================================
# Excel Database share links
# ============================================================
CHART_EXCEL_SHARE_LINK = os.getenv(
    "CHART_EXCEL_SHARE_LINK",
    "https://aeondelight-my.sharepoint.com/:x:/g/personal/giap_dinh_aeondelight_biz/IQAb8OXh4IXMSrzp7jx-lDj6AbPi1HRYxxFgMT5udTOGfHo?e=Thpkbx"
)

STATUS_EXCEL_SHARE_LINK = os.getenv(
    "STATUS_EXCEL_SHARE_LINK",
    "https://aeondelight-my.sharepoint.com/:x:/g/personal/giap_dinh_aeondelight_biz/IQCFCqbb6bp0TZnixsmUNXaHAaGxjypLKvc0Lj9UvogF4og"
)

# ============================================================
# OneDrive subfolder paths (relative from ROOT)
# ============================================================
# FOR AEONMALL
NVL_REPORT_FORM_PATH   = "REPORT FORM/NVL REPORT FORM"
TQB_REPORT_FORM_PATH   = "REPORT FORM/TQB REPORT FORM"
BDNC_REPORT_FORM_PATH  = "REPORT FORM/BDNC REPORT FORM"
VG_REPORT_FORM_PATH    = "REPORT FORM/VG REPORT FORM"
MDR_REPORT_FORM_PATH   = "REPORT FORM/MDR REPORT FORM"

# FOR MAXVALUE
LACASTA_REPORT_FORM_PATH = "REPORT FORM/MAXVALUE/LACASTA"

# HOTLINES & CONFIRM FORM
HOTLINES_AND_CONFIRM_FORM_PATH = "HOTLINE_AND_CONFIRM_FORM"

# DAVITEQ IMAGE ARCHIVE
GATEWAY_BDNC_PATH = "DAVITEQ/IMAGE_ ARCHIVE/GATEWAY/BDNC"
GATEWAY_TQB_PATH  = "DAVITEQ/IMAGE_ ARCHIVE/GATEWAY/TQB"
GATEWAY_NVL_PATH  = "DAVITEQ/IMAGE_ ARCHIVE/GATEWAY/NVL"
GATEWAY_VG_PATH   = ""  # PENDING

LAYOUT_BDNC_PATH  = "DAVITEQ/IMAGE_ ARCHIVE/LAYOUT/BDNC"
LAYOUT_TQB_PATH   = "DAVITEQ/IMAGE_ ARCHIVE/LAYOUT/TQB"
LAYOUT_NVL_PATH   = "DAVITEQ/IMAGE_ ARCHIVE/LAYOUT/NVL"
LAYOUT_VG_PATH    = "DAVITEQ/IMAGE_ ARCHIVE/LAYOUT/VG"

SENSOR_BDNC_PATH  = "DAVITEQ/IMAGE_ ARCHIVE/SENSOR/BDNC"
SENSOR_TQB_PATH   = "DAVITEQ/IMAGE_ ARCHIVE/SENSOR/TQB"
SENSOR_NVL_PATH   = "DAVITEQ/IMAGE_ ARCHIVE/SENSOR/NVL"
SENSOR_VG_PATH    = ""  # PENDING

AL_NVL_PATH       = "DAVITEQ/IMAGE_ ARCHIVE/ALARM POINTS/NVL"
AL_TQB_PATH       = "DAVITEQ/IMAGE_ ARCHIVE/ALARM POINTS/TQB"
AL_BDNC_PATH      = ""  # NOT AVAILABLE
AL_VG_PATH        = "DAVITEQ/IMAGE_ ARCHIVE/ALARM POINTS/VG"

# DOCUMENTARY
DOCUMENTARY_PATH = "DOCUMENTARY"

# ============================================================
# Local storage directories
# ============================================================
# Normalize BASE_DIR for Linux/Docker environment
BASE_DIR = os.getenv("RMC_BASE_DIR", "C:/RMC_Assistant_ver2.0").replace("\\", "/")
if os.name != 'nt' and not BASE_DIR.startswith("/"):
    # If on Linux and BASE_DIR looks like a Windows path but RMC_BASE_DIR env is missing
    BASE_DIR = "/data"

CACHE_DIR              = os.path.join(BASE_DIR, "Cache")
CACHE_FILE             = os.path.join(CACHE_DIR, "token_cache.bin")
REPORT_FORM_DIR        = os.path.join(BASE_DIR, "Report_Form_Cache")
NOTE_ARCHIVE_DIR       = os.path.join(BASE_DIR, "NOTE")
IMAGE_LAYOUT_DIR       = os.path.join(BASE_DIR, "IMAGE", "LAYOUT")
IMAGE_GATEWAY_DIR      = os.path.join(BASE_DIR, "IMAGE", "GATEWAY")
IMAGE_SENSOR_DIR       = os.path.join(BASE_DIR, "IMAGE", "SENSOR")
DEBUG_LOG_PATH         = os.path.join(BASE_DIR, "excel_debug.log")
IMAGE_AL_DIR           = os.path.join(BASE_DIR, "IMAGE", "ALARMPOINT")
DOCUMENTARY_ARCHIVE_DIR = os.path.join(BASE_DIR, "DOCUMENTARY")
METADATA_DIR           = os.path.join(BASE_DIR, "METADATA")
METADATA_FILE          = os.path.join(METADATA_DIR, "onedrive_metadata.json")
USERS_DB_FILE          = os.path.join(METADATA_DIR, "users.json")

# Image category → local dir mapping
IMAGE_CATEGORY_DIR = {
    "LAYOUT":     IMAGE_LAYOUT_DIR,
    "GATEWAY":    IMAGE_GATEWAY_DIR,
    "SENSOR":     IMAGE_SENSOR_DIR,
    "ALARMPOINT": IMAGE_AL_DIR,
}

# Image category → site → OneDrive path
IMAGE_PATHS = {
    "GATEWAY": {
        "BDNC": GATEWAY_BDNC_PATH,
        "TQB":  GATEWAY_TQB_PATH,
        "NVL":  GATEWAY_NVL_PATH,
    },
    "LAYOUT": {
        "BDNC": LAYOUT_BDNC_PATH,
        "TQB":  LAYOUT_TQB_PATH,
        "NVL":  LAYOUT_NVL_PATH,
        "VG":   LAYOUT_VG_PATH,
    },
    "SENSOR": {
        "BDNC": SENSOR_BDNC_PATH,
        "TQB":  SENSOR_TQB_PATH,
        "NVL":  SENSOR_NVL_PATH,
    },
    "ALARMPOINT": {
        "TQB": AL_TQB_PATH,
        "NVL": AL_NVL_PATH,
        "VG":  AL_VG_PATH,
    },
}

# Sites config: group -> list_key -> OneDrive path
# Key = ten hien thi tren web, value = duong dan OneDrive
SITES_CONFIG = {
    "AEONMALL": {
        "AEON Nguyen Van Linh": NVL_REPORT_FORM_PATH,
        "AEON Ta Quang Buu":    TQB_REPORT_FORM_PATH,
        "AEON Binh Duong NC":   BDNC_REPORT_FORM_PATH,
        "AEON Van Giang":       VG_REPORT_FORM_PATH,
        "AEON Midori":          MDR_REPORT_FORM_PATH,
    },
    "MAXVALUE": {
        "LaCasta": LACASTA_REPORT_FORM_PATH,
    },
}

# Map ten site -> site key
# Key la ten UPPERCASE khong dau (cach browser gui len)
SITE_KEY_MAP = {
    "AEON NGUYEN VAN LINH": "ANVL",
    "AEON TA QUANG BUU":    "TQB",
    "AEON BINH DUONG NC":   "ABNC",
    "AEON VAN GIANG":       "AVG",
    "AEON MIDORI":          "Midori",
    "LACASTA":              "LACASTA",
    # ten goc co dau (fallback)
    "AEON Nguyen Van Linh": "ANVL",
    "AEON Ta Quang Buu":    "TQB",
    "AEON Binh Duong NC":   "ABNC",
    "AEON Van Giang":       "AVG",
    "AEON Midori":          "Midori",
    "LaCasta":              "LACASTA",
}

# ============================================================
# Rate Limiting Configuration
# Tất cả giá trị đọc từ .env, có fallback mặc định hợp lý.
# Đặt RATE_LIMIT_ENABLED=false để tắt hoàn toàn (dùng khi debug).
# ============================================================
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"

# Login / Brute-force protection (per IP)
RATE_LIMIT_LOGIN_MAX    = int(os.getenv("RATE_LIMIT_LOGIN_MAX",    "5"))    # 5 lần/60s
RATE_LIMIT_LOGIN_PERIOD = int(os.getenv("RATE_LIMIT_LOGIN_PERIOD", "60"))   # window 60s
RATE_LIMIT_LOGIN_BLOCK  = int(os.getenv("RATE_LIMIT_LOGIN_BLOCK",  "300"))  # block 5 phút

# General API — Global (per IP)
RATE_LIMIT_API_MAX      = int(os.getenv("RATE_LIMIT_API_MAX",    "100"))   # 100 req/60s
RATE_LIMIT_API_PERIOD   = int(os.getenv("RATE_LIMIT_API_PERIOD", "60"))    # window 60s
RATE_LIMIT_API_BLOCK    = int(os.getenv("RATE_LIMIT_API_BLOCK",  "60"))    # block 60s

# General API — Per authenticated user
RATE_LIMIT_USER_MAX     = int(os.getenv("RATE_LIMIT_USER_MAX",   "200"))   # 200 req/60s

# Heavy / expensive operations (per user)
RATE_LIMIT_HEAVY_MAX    = int(os.getenv("RATE_LIMIT_HEAVY_MAX",    "10"))   # 10 req/60s
RATE_LIMIT_HEAVY_PERIOD = int(os.getenv("RATE_LIMIT_HEAVY_PERIOD", "60"))
RATE_LIMIT_HEAVY_BLOCK  = int(os.getenv("RATE_LIMIT_HEAVY_BLOCK",  "120"))  # block 2 phút



# OneDrive sync trigger (per IP) — rất tốn kém
RATE_LIMIT_SYNC_MAX     = int(os.getenv("RATE_LIMIT_SYNC_MAX",    "3"))    # 3 lần/5 phút
RATE_LIMIT_SYNC_PERIOD  = int(os.getenv("RATE_LIMIT_SYNC_PERIOD", "300"))  # window 5 phút
RATE_LIMIT_SYNC_BLOCK   = int(os.getenv("RATE_LIMIT_SYNC_BLOCK",  "600"))  # block 10 phút

# Admin endpoints (per IP)
RATE_LIMIT_ADMIN_MAX    = int(os.getenv("RATE_LIMIT_ADMIN_MAX",    "30"))   # 30 req/60s
RATE_LIMIT_ADMIN_PERIOD = int(os.getenv("RATE_LIMIT_ADMIN_PERIOD", "60"))
RATE_LIMIT_ADMIN_BLOCK  = int(os.getenv("RATE_LIMIT_ADMIN_BLOCK",  "120"))


# ============================================================
# Create all local directories on import
# ============================================================
for _dir in [
    CACHE_DIR, REPORT_FORM_DIR, NOTE_ARCHIVE_DIR,
    IMAGE_LAYOUT_DIR, IMAGE_GATEWAY_DIR, IMAGE_SENSOR_DIR, IMAGE_AL_DIR,
    DOCUMENTARY_ARCHIVE_DIR, METADATA_DIR,
]:
    try:
        os.makedirs(_dir, exist_ok=True)
    except Exception as e:
        print(f"WARN: Could not create directory {_dir}: {e}")