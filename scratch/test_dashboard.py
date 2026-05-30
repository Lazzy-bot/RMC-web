import sys
import os

# Add backend to path
sys.path.append(os.path.abspath("backend"))

try:
    # When backend is in path, we import directly from services
    from services.excel import get_comprehensive_dashboard_data
    print("Function imported successfully.")
    # data = get_comprehensive_dashboard_data(start_date_str="2026-01-01", end_date_str="2026-12-31")
    # print("Success! Data keys:", data.keys())
except Exception as e:
    import traceback
    print("Error occurred:")
    traceback.print_exc()
