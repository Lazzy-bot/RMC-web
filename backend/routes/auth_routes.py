from flask import Blueprint, jsonify, redirect, request, url_for
import traceback
import requests as _requests
from config import PUBLIC_BASE_URL, MS_OAUTH_CLIENT_ID, MS_OAUTH_CLIENT_SECRET, MS_OAUTH_TENANT_ID

from auth import (
    add_user_by_admin,
    approve_user,
    clear_session_user,
    delete_user,
    get_enabled_providers,
    get_oauth_client,
    get_session_user,
    graph_session,
    list_users,
    set_session_user,
    update_user_role,
    upsert_user_from_oauth,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _can_access(user: dict | None) -> bool:
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    return bool(user.get("approved", False))


@auth_bp.get("/providers")
def auth_providers():
    return jsonify({"providers": get_enabled_providers()})


@auth_bp.get("/me")
def me():
    user = get_session_user()
    return jsonify(
        {
            "logged_in": bool(user),
            "can_access": _can_access(user),
            "user": user,
            "providers": get_enabled_providers(),
            "graph_authenticated": graph_session.is_authenticated,  # Giờ trả về ngay từ cache
        }
    )


@auth_bp.get("/status")
def auth_status():
    """Backward-compatible status endpoint used by frontend auth bootstrap."""
    user = get_session_user()
    return jsonify(
        {
            "authenticated": _can_access(user),
            "logged_in": bool(user),
            "approved": bool(user.get("approved", False)) if user else False,
            "user": user,
        }
    )


@auth_bp.post("/logout")
def logout():
    clear_session_user()
    return jsonify({"ok": True})


@auth_bp.get("/login/<provider>")
def login(provider: str):
    provider = provider.lower().strip()
    client = get_oauth_client(provider)
    if not client:
        return jsonify({"error": f"Provider '{provider}' chưa được cấu hình"}), 400

    if PUBLIC_BASE_URL:
        redirect_uri = f"{PUBLIC_BASE_URL}/api/auth/callback/{provider}"
    else:
        redirect_uri = url_for("auth.auth_callback", provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


def _ms_exchange_code(code: str, redirect_uri: str) -> dict:
    """
    Thực hiện token exchange với Microsoft trực tiếp bằng requests.post.
    Đảm bảo client_secret luôn nằm trong POST body (AADSTS7000218 fix).
    """
    token_url = (
        f"https://login.microsoftonline.com/{MS_OAUTH_TENANT_ID}"
        f"/oauth2/v2.0/token"
    )
    print(f"[MS EXCHANGE] token_url={token_url}", flush=True)
    print(f"[MS EXCHANGE] redirect_uri={redirect_uri}", flush=True)
    print(f"[MS EXCHANGE] client_id={MS_OAUTH_CLIENT_ID}", flush=True)
    print(f"[MS EXCHANGE] secret_len={len(MS_OAUTH_CLIENT_SECRET)} secret_ok={bool(MS_OAUTH_CLIENT_SECRET)}", flush=True)
    print(f"[MS EXCHANGE] code_len={len(code)} code_empty={not code}", flush=True)

    resp = _requests.post(
        token_url,
        data={
            "grant_type":    "authorization_code",
            "client_id":     MS_OAUTH_CLIENT_ID,
            "client_secret": MS_OAUTH_CLIENT_SECRET,
            "code":          code,
            "redirect_uri":  redirect_uri,
            "scope":         "openid profile email User.Read",
        },
        timeout=15,
    )
    print(f"[MS EXCHANGE] HTTP status={resp.status_code}", flush=True)
    token = resp.json()
    if "error" in token:
        print(f"[MS EXCHANGE] ERROR={token.get('error')} DESC={token.get('error_description', '')[:300]}", flush=True)
        raise RuntimeError(
            f"MS token exchange error: {token.get('error')} – "
            f"{token.get('error_description', '')}"
        )
    print(f"[MS EXCHANGE] SUCCESS token_type={token.get('token_type')}", flush=True)
    return token


@auth_bp.get("/callback/<provider>")
def auth_callback(provider: str):
    provider = provider.lower().strip()
    print(f"[AUTH CALLBACK] provider={provider} args={dict(request.args)}", flush=True)

    client = get_oauth_client(provider)
    if not client:
        return redirect("/?auth=provider_not_configured")

    # Phát hiện Microsoft trả về lỗi TRONG redirect URL (trước khi exchange code)
    ms_error = request.args.get("error", "")
    if ms_error:
        ms_error_desc = request.args.get("error_description", "")
        print(f"[AUTH CALLBACK] Microsoft returned error in redirect: {ms_error} – {ms_error_desc[:300]}", flush=True)
        return redirect(f"/?auth=failed&reason={ms_error}")

    try:
        if provider == "microsoft":
            # Bypass Authlib token exchange: gọi thẳng requests.post
            # để đảm bảo client_secret nằm trong body (AADSTS7000218).
            code = request.args.get("code", "")
            if not code:
                print("[AUTH CALLBACK] ERROR: no code in Microsoft callback!", flush=True)
                return redirect("/?auth=failed&reason=no_code")
            if PUBLIC_BASE_URL:
                redirect_uri = f"{PUBLIC_BASE_URL}/api/auth/callback/microsoft"
            else:
                redirect_uri = url_for("auth.auth_callback", provider="microsoft", _external=True)
            token = _ms_exchange_code(code, redirect_uri)
        else:
            token = client.authorize_access_token()

        user = upsert_user_from_oauth(provider, token, client)
        set_session_user(user)

        if user.get("role") == "admin" or user.get("approved"):
            return redirect("/?auth=success")
        return redirect("/?auth=pending")
    except Exception as e:
        print(f"[AUTH CALLBACK ERROR] provider={provider} error={e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return redirect("/?auth=failed")


@auth_bp.get("/admin/users")
def admin_users():
    user = get_session_user()
    if not user or user.get("role") != "admin":
        return jsonify({"error": "Bạn không có quyền admin"}), 403
    return jsonify(list_users())


@auth_bp.post("/admin/users")
def admin_add_user():
    user = get_session_user()
    if not user or user.get("role") != "admin":
        return jsonify({"error": "Bạn không có quyền admin"}), 403

    body = request.json or {}
    email = body.get("email", "")
    name = body.get("name", "")
    approved = bool(body.get("approved", True))

    try:
        created = add_user_by_admin(email=email, name=name, approved=approved)
        return jsonify(created), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.post("/admin/users/<user_id>/approve")
def admin_approve_user(user_id: str):
    user = get_session_user()
    if not user or user.get("role") != "admin":
        return jsonify({"error": "Bạn không có quyền admin"}), 403

    try:
        approved_user = approve_user(user_id)
        return jsonify(approved_user)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.delete("/admin/users/<user_id>")
def admin_delete_user(user_id: str):
    user = get_session_user()
    if not user or user.get("role") != "admin":
        return jsonify({"error": "Bạn không có quyền admin"}), 403

    try:
        delete_user(user_id)
        return jsonify({"deleted": user_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.post("/admin/users/<user_id>/role")
def admin_update_user_role(user_id: str):
    user = get_session_user()
    if not user or user.get("role") != "admin":
        return jsonify({"error": "Bạn không có quyền admin"}), 403

    body = request.json or {}
    new_role = body.get("role", "")

    try:
        updated = update_user_role(user_id, new_role)
        return jsonify(updated)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@auth_bp.post("/graph/device-flow")
def start_device_flow():
    """
    Khởi động device flow.
    Frontend dùng user_code và verification_uri để hiển thị cho user.
    """
    try:
        result = graph_session.start_device_flow()
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e), "message": str(e)}), 500


@auth_bp.get("/graph/device-flow/poll")
def poll_device_flow():
    """Frontend poll endpoint này để biết khi nào login hoàn tất."""
    result = graph_session.check_device_flow_result()
    return jsonify(result)


# Backward-compat aliases
@auth_bp.post("/device-flow")
def start_device_flow_compat():
    return start_device_flow()


@auth_bp.get("/device-flow/poll")
def poll_device_flow_compat():
    return poll_device_flow()
