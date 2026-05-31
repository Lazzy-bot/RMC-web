import os
import time
import threading
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from auth import get_session_user, init_oauth, init_user_store
from config import APP_SECRET_KEY
from routes import auth_bp, report_bp, contact_bp, note_bp, image_bp, docs_bp, slack_bp, admin_mgmt_bp
from services.note import reload_all_schedules


def create_app() -> Flask:
    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "..", "frontend"),
        static_url_path="",
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.secret_key = APP_SECRET_KEY
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = False  # Set to True if using HTTPS
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 30 # 30 days
    CORS(app, supports_credentials=True)

    init_user_store()
    init_oauth(app)

    def load_schedules_async(app):
        def run():
            time.sleep(2)
            try:
                with app.app_context():
                    reload_all_schedules()
            except Exception as e:
                app.logger.error(f"Async loading schedules error: {e}")

        threading.Thread(target=run, daemon=True).start()

    load_schedules_async(app)

    @app.before_request
    def enforce_user_access():
        path = request.path

        if not path.startswith("/api"):
            return None

        # Public endpoints required for sign-in flow
        if path in {"/api/auth/providers", "/api/auth/me", "/api/auth/status", "/api/auth/logout"}:
            return None
        if path.startswith("/api/auth/login/") or path.startswith("/api/auth/callback/"):
            return None

        user = get_session_user()
        if not user:
            return jsonify({"error": "Vui lòng đăng nhập", "code": "not_authenticated"}), 401

        is_admin = user.get("role") == "admin"
        approved = bool(user.get("approved", False))

        if (path.startswith("/api/auth/admin") or path.startswith("/api/admin")) and not is_admin:
            return jsonify({"error": "Bạn không có quyền admin", "code": "not_admin"}), 403

        if not is_admin and not approved:
            return jsonify({"error": "Tài khoản đang chờ admin phê duyệt", "code": "pending_approval"}), 403

        return None

    @app.after_request
    def disable_api_caching(response):
        if request.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            # Thêm header thông báo cho browser biết server đã trả lời (tránh treo)
            response.headers["X-Request-Completed"] = "true"
        return response

    for bp in [auth_bp, report_bp, contact_bp, note_bp, image_bp, docs_bp, slack_bp, admin_mgmt_bp]:
        app.register_blueprint(bp)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
        if path and os.path.exists(os.path.join(frontend_dir, path)):
            return send_from_directory(frontend_dir, path)
        return send_from_directory(frontend_dir, "index.html")

    return app


# Gunicorn entrypoint (Docker)
wsgi_app = create_app()

if __name__ == "__main__":
    print("RMC Assistant dang chay tai http://localhost:5000")
    wsgi_app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)