import os
import sys
import json
import time
import requests

# Thêm thư mục backend vào python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from auth.azure_auth import graph_session, MANUAL_TOKEN_FILE, CLIENT_ID, TENANT_ID, GRAPH_SCOPES, AZURE_CLIENT_SECRET

print("=== MSAL & MANUAL TOKEN REFRESH TEST ===")
print("MANUAL_TOKEN_FILE path:", MANUAL_TOKEN_FILE)
print("File exists:", os.path.exists(MANUAL_TOKEN_FILE))

if os.path.exists(MANUAL_TOKEN_FILE):
    try:
        with open(MANUAL_TOKEN_FILE, "r") as f:
            token_data = json.load(f)
        print("Token scopes inside file:", token_data.get("scope"))
        print("Has refresh_token:", "refresh_token" in token_data)
        
        refresh_token = token_data.get("refresh_token")
        
        # Test 1: WITH client secret
        print("\n--- Test 1: Refresh WITH client secret ---")
        token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
        data = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(GRAPH_SCOPES),
            "client_secret": AZURE_CLIENT_SECRET
        }
        r = requests.post(token_url, data=data, timeout=10)
        print("Status Code:", r.status_code)
        print("Response:", r.text[:300])
        
        # Test 2: WITHOUT client secret
        print("\n--- Test 2: Refresh WITHOUT client secret ---")
        data_no_secret = {
            "client_id": CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": " ".join(GRAPH_SCOPES)
        }
        r2 = requests.post(token_url, data=data_no_secret, timeout=10)
        print("Status Code:", r2.status_code)
        print("Response:", r2.text[:300])
        
    except Exception as e:
        print("Error reading token file:", e)
