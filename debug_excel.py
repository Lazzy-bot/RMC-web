import os
import sys
import json
import base64
import requests

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.auth import graph_session
from backend.config import CHART_EXCEL_SHARE_LINK

def debug_excel():
    print("--- DEBUG EXCEL START ---")
    try:
        token = graph_session.ensure_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        clean_link = CHART_EXCEL_SHARE_LINK.strip().split("?")[0]
        encoded = base64.b64encode(clean_link.encode("utf-8")).decode("utf-8").rstrip("=").replace("/", "_").replace("+", "-")
        
        # 1. Resolve Item
        r = requests.get(f"https://graph.microsoft.com/v1.0/shares/u!{encoded}/driveItem", headers=headers)
        if r.status_code != 200:
            print(f"Error resolving item: {r.status_code} {r.text}")
            return
        
        item = r.json()
        drive_id = item["parentReference"]["driveId"]
        item_id = item["id"]
        print(f"Drive ID: {drive_id}")
        print(f"Item ID: {item_id}")
        
        # 2. List Sheets
        r = requests.get(f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets", headers=headers)
        sheets = [s["name"] for s in r.json().get("value", [])]
        print(f"Available Sheets: {sheets}")
        
        target = "Processing Results" if "Processing Results" in sheets else "Sheet1"
        if target not in sheets and sheets: target = sheets[0]
        print(f"Targeting Sheet: {target}")
        
        # 3. Get usedRange
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{item_id}/workbook/worksheets('{target}')/usedRange"
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            print(f"Error getting usedRange: {r.status_code} {r.text}")
            return
        
        data = r.json()
        address = data.get("address", "")
        values = data.get("values", [])
        print(f"Address: {address}")
        print(f"Total Rows Found: {len(values)}")
        
        if len(values) > 0:
            print("First 5 rows:")
            for i, row in enumerate(values[:5]):
                print(f"Row {i+1}: {row}")
        
        if len(values) > 8:
            print("Row 9 (Sample Data?):")
            print(f"Row 9: {values[8]}")

    except Exception as e:
        print(f"Exception during debug: {str(e)}")
    print("--- DEBUG EXCEL END ---")

if __name__ == "__main__":
    debug_excel()
