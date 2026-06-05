import os
import time
import threading
from flask import Flask, jsonify, request, send_from_directory, g
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from auth import get_session_user, init_oauth, init_user_store
from config import APP_SECRET_KEY, RATE_LIMIT_ENABLED
from routes import auth_bp, report_bp, contact_bp, note_bp, image_bp, docs_bp, admin_mgmt_bp
from services.note import reload_all_schedules
from rate_limiter import (
    login_limiter,
    api_ip_limiter,
    api_user_limiter,
    heavy_limiter,
    sync_limiter,
    admin_limiter,
)


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

    # FIX: Pre-warm dashboard cache ở background khi app khởi động
    # Tránh user đầu tiên bị chờ lâu do cold start OneDrive call
    def _prewarm_dashboard(app):
        def run():
            import time
            time.sleep(5)  # Đợi app sẵn sàng hoàn toàn
            try:
                with app.app_context():
                    from services.excel import _load_dashboard_raw
                    _load_dashboard_raw()
                    app.logger.info("Dashboard cache pre-warmed successfully.")
            except Exception as e:
                app.logger.warning(f"Dashboard cache pre-warm failed (will retry on first request): {e}")
        threading.Thread(target=run, daemon=True).start()

    _prewarm_dashboard(app)

    def _rate_limited_response(retry_after: int) -> tuple:
        """Trả về HTTP 429 chuẩn với Retry-After header."""
        resp = jsonify({
            "error": "Quá nhiều yêu cầu. Vui lòng thử lại sau.",
            "code":  "rate_limited",
            "retry_after": retry_after,
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        resp.headers["X-RateLimit-Remaining"] = "0"
        return resp

    @app.before_request
    def start_timer():
        g.start_time = time.time()

    @app.before_request
    def enforce_user_access():
        path = request.path
        client_ip = request.remote_addr or "unknown"

        if not path.startswith("/api"):
            return None

        # ── Rate Limiting ─────────────────────────────────────────────────
        if RATE_LIMIT_ENABLED and client_ip not in ("127.0.0.1", "::1"):
            # 1. Brute-force protection cho login (per IP, rất nghiêm ngặt)
            if path.startswith("/api/auth/login/"):
                allowed, retry_after = login_limiter.is_allowed(client_ip)
                if not allowed:
                    app.logger.warning(
                        f"[RATE LIMIT] login blocked: ip={client_ip} retry_after={retry_after}s"
                    )
                    return _rate_limited_response(retry_after)

            # 2. Sync endpoint — cực kỳ tốn kém, giới hạn chặt (per IP)
            elif path == "/api/sync":
                allowed, retry_after = sync_limiter.is_allowed(client_ip)
                if not allowed:
                    app.logger.warning(
                        f"[RATE LIMIT] sync blocked: ip={client_ip} retry_after={retry_after}s"
                    )
                    return _rate_limited_response(retry_after)

            # 3. Tất cả API khác — global per-IP limit
            elif not path.startswith("/api/auth/callback/"):
                allowed, retry_after = api_ip_limiter.is_allowed(client_ip)
                if not allowed:
                    app.logger.warning(
                        f"[RATE LIMIT] api_ip blocked: ip={client_ip} retry_after={retry_after}s"
                    )
                    return _rate_limited_response(retry_after)

            # Lưu ip vào g để after_request dùng cho headers
            g.rl_ip = client_ip
            g.rl_path = path

        # ── Auth Check ────────────────────────────────────────────────────
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

        # ── Per-user + Heavy endpoint limits (chỉ áp dụng sau khi xác thực) ──
        if RATE_LIMIT_ENABLED and client_ip not in ("127.0.0.1", "::1"):
            user_key = user.get("email") or user.get("id") or client_ip

            # Per-user global throttle (admin bỏ qua)
            if not is_admin:
                allowed, retry_after = api_user_limiter.is_allowed(user_key)
                if not allowed:
                    app.logger.warning(
                        f"[RATE LIMIT] api_user blocked: user={user_key} retry_after={retry_after}s"
                    )
                    return _rate_limited_response(retry_after)

            # Heavy endpoints: sync, charts, dashboard, report text
            _HEAVY_PREFIXES = (
                "/api/sync",
                "/api/charts",
                "/api/dashboard",
                "/api/report/text",
            )
            if path.startswith(_HEAVY_PREFIXES):
                allowed, retry_after = heavy_limiter.is_allowed(user_key)
                if not allowed:
                    app.logger.warning(
                        f"[RATE LIMIT] heavy blocked: user={user_key} path={path} retry_after={retry_after}s"
                    )
                    return _rate_limited_response(retry_after)


            # Admin endpoints (per IP — thêm lớp bảo vệ ngoài auth)
            if path.startswith("/api/admin") or path.startswith("/api/auth/admin"):
                allowed, retry_after = admin_limiter.is_allowed(client_ip)
                if not allowed:
                    app.logger.warning(
                        f"[RATE LIMIT] admin blocked: ip={client_ip} retry_after={retry_after}s"
                    )
                    return _rate_limited_response(retry_after)

            # Lưu user key để after_request thêm headers
            g.rl_user_key = user_key

        return None

    @app.after_request
    def disable_api_caching(response):
        if request.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            # Thêm header thông báo cho browser biết server đã trả lời (tránh treo)
            response.headers["X-Request-Completed"] = "true"
            # Log thời gian xử lý để debug nếu cần
            if hasattr(g, 'start_time'):
                duration = time.time() - g.start_time
                response.headers["X-Process-Time"] = f"{duration:.3f}s"

            # Thêm RateLimit headers để client biết trạng thái limit hiện tại
            if RATE_LIMIT_ENABLED:
                client_ip = getattr(g, "rl_ip", request.remote_addr or "unknown")
                remaining = api_ip_limiter.get_remaining(client_ip)
                reset_ts  = api_ip_limiter.get_reset_time(client_ip)
                response.headers["X-RateLimit-Limit"]     = str(api_ip_limiter.max_calls)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Reset"]     = str(reset_ts)
                response.headers["X-RateLimit-Policy"]    = (
                    f"{api_ip_limiter.max_calls};w={api_ip_limiter.period}"
                )
        return response

    for bp in [auth_bp, report_bp, contact_bp, note_bp, image_bp, docs_bp, admin_mgmt_bp]:
        app.register_blueprint(bp)

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

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