import os
import sys
import json
import time

# Thêm thư mục backend vào python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from auth.azure_auth import graph_session, MANUAL_TOKEN_FILE

print("=== TESTING GRAD_SESSION CLASS METHODS ===")
print("MANUAL_TOKEN_FILE path:", MANUAL_TOKEN_FILE)
print("File exists:", os.path.exists(MANUAL_TOKEN_FILE))

print("\n--- Testing refresh_token_manually() ---")
try:
    token = graph_session.refresh_token_manually()
    if token:
        print("✅ Success! refresh_token_manually() returned a valid token!")
        print("Token snippet:", token[:30] + "..." + token[-30:])
    else:
        print("❌ Failed! refresh_token_manually() returned None")
except Exception as e:
    print("❌ Exception in refresh_token_manually():", e)

print("\n--- Testing get_valid_token() ---")
try:
    token = graph_session.get_valid_token()
    if token:
        print("✅ Success! get_valid_token() returned a valid token!")
        print("Token snippet:", token[:30] + "..." + token[-30:])
    else:
        print("❌ Failed! get_valid_token() returned None")
except Exception as e:
    print("❌ Exception in get_valid_token():", e)
