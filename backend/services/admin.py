import os
import json
from config import METADATA_DIR, SITES_CONFIG, SITE_KEY_MAP

SITES_FILE = os.path.join(METADATA_DIR, "sites_v2.json")
DEVICES_FILE = os.path.join(METADATA_DIR, "devices.json")
PICS_FILE = os.path.join(METADATA_DIR, "pics.json")

def load_sites_config():
    """
    Load SITES_CONFIG and SITE_KEY_MAP from JSON.
    If not exists, initialize from config.py defaults.
    """
    if os.path.exists(SITES_FILE):
        try:
            with open(SITES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("SITES_CONFIG", {}), data.get("SITE_KEY_MAP", {})
        except Exception as e:
            print(f"ERROR: Error loading sites.json: {e}")
    
    # Default from config.py
    return SITES_CONFIG, SITE_KEY_MAP

def save_sites_config(sites_config, site_key_map):
    """Save SITES_CONFIG and SITE_KEY_MAP to JSON."""
    data = {
        "SITES_CONFIG": sites_config,
        "SITE_KEY_MAP": site_key_map
    }
    with open(SITES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_devices_list():
    """Load common devices list for datalists."""
    if os.path.exists(DEVICES_FILE):
        try:
            with open(DEVICES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"ERROR: Error loading devices.json: {e}")
    
    # Default defaults (from index.html hardcoded list)
    return [
        "Food refrigeration system & showcase", "Power Supply", "LPG Alarm",
        "KEF/ KSF Fan", "Delica", "Sushi", "Bakery", "Power Supply-Aeon 1",
        "Power Supply-Aeon 2", "Power Supply-Aeon 3", "None", "Security",
        "Meat Kitchen", "Product Kitchen", "CF counter", "Noodle",
        "Fish Kitchen", "OF/EF Fan", "Power_MDB-1F", "Power_MDB-2F",
        "BMS", "Socket", "Server", "Generator", "Fire Pump", "WS Treatment",
        "High Level Water", "Low Level Water", "WS Pump Trip", "Tu dong 3 cua",
        "Tu kem", "Tu dong nam", "Tu showcase", "PIR Light Sensor"
    ]

def save_devices_list(devices):
    """Save common devices list to JSON."""
    with open(DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, ensure_ascii=False, indent=2)

def load_pics_list():
    """Load PICs list for datalists."""
    if os.path.exists(PICS_FILE):
        try:
            with open(PICS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"ERROR: Error loading pics.json: {e}")
    
    # Default PICs if none exist
    return ["Mr. Dũng", "Mr. Giáp", "Mr. An", "Mr. Bình", "Mr. Quang", "Mr. Tuấn"]

def save_pics_list(pics):
    """Save PICs list to JSON."""
    with open(PICS_FILE, "w", encoding="utf-8") as f:
        json.dump(pics, f, ensure_ascii=False, indent=2)
