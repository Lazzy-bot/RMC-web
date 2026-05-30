import os
import sys

# Add backend to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from services.excel import append_status_to_excel
from config import CHART_EXCEL_SHARE_LINK

def test_write():
    print(f"Testing write to: {CHART_EXCEL_SHARE_LINK}")
    try:
        res = append_status_to_excel(
            site_name="ATD",
            device="Fan",
            pic="Mr. Giáp",
            alarm_type="Operation",
            alarm_level="Low",
            status="Done",
            description="Mẫu test",
            processing="Đã xử lý",
            week="Week 2",
            start_time="21:11",
            start_date="2026-05-16",
            end_time="22:16",
            end_date="2026-05-16"
        )
        print(f"Success: {res}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_write()
