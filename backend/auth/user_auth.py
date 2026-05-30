import json
import os
import threading
import uuid
from datetime import datetime, timezone

from authlib.integrations.flask_client import OAuth
from flask import session

from config import (
    ADMIN_EMAILS,
    GOOGLE_OAUTH_CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET,
    MS_OAUTH_CLIENT_ID,
    MS_OAUTH_CLIENT_SECRET,
    MS_OAUTH_TENANT_ID,
    USERS_DB_FILE,
)

_oauth = OAuth()
_clients = {}
_db_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _default_db() -> dict:
    return {"users": []}


def _read_db() -> dict:
    os.makedirs(os.path.dirname(USERS_DB_FILE), exist_ok=True)
    if not os.path.exists(USERS_DB_FILE):
        return _default_db()

    try:
        with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("users"), list):
            return data
    except Exception:
        pass
    return _default_db()


def _write_db(data: dict) -> None:
    os.makedirs(os.path.dirname(USERS_DB_FILE), exist_ok=True)
    with open(USERS_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _public_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name", ""),
        "provider": user.get("provider", ""),
        "role": user.get("role", "user"),
        "approved": bool(user.get("approved", False)),
        "created_at": user.get("created_at"),
        "last_login_at": user.get("last_login_at"),
    }


def _ensure_admin_seed(db: dict) -> bool:
    changed = False
    users = db.get("users", [])

    for admin_email in ADMIN_EMAILS:
        email = _normalize_email(admin_email)
        if not email:
            continue
        found = next((u for u in users if _normalize_email(u.get("email")) == email), None)
        if found:
            if found.get("role") != "admin" or not found.get("approved", False):
                found["role"] = "admin"
                found["approved"] = True
                found.setdefault("name", "Admin")
                found.setdefault("provider", "seed")
                changed = True
            continue

        users.append(
            {
                "id": str(uuid.uuid4()),
                "email": email,
                "name": "Admin",
                "provider": "seed",
                "role": "admin",
                "approved": True,
                "created_at": _now_iso(),
                "last_login_at": None,
            }
        )
        changed = True

    return changed


def init_user_store() -> None:
    with _db_lock:
        db = _read_db()
        if _ensure_admin_seed(db):
            _write_db(db)


def init_oauth(app) -> None:
    _oauth.init_app(app)

    _clients.clear()

    if MS_OAUTH_CLIENT_ID and MS_OAUTH_CLIENT_SECRET:
        _clients["microsoft"] = _oauth.register(
            name="microsoft",
            client_id=MS_OAUTH_CLIENT_ID,
            client_secret=MS_OAUTH_CLIENT_SECRET,
            server_metadata_url=f"https://login.microsoftonline.com/{MS_OAUTH_TENANT_ID}/v2.0/.well-known/openid-configuration",
            # token_endpoint_auth_method MUST be inside client_kwargs in Authlib 1.3.x
            # so it is applied to the actual token-exchange POST request.
            client_kwargs={
                "scope": "openid profile email User.Read",
                "token_endpoint_auth_method": "client_secret_post",
            },
        )

    if GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET:
        _clients["google"] = _oauth.register(
            name="google",
            client_id=GOOGLE_OAUTH_CLIENT_ID,
            client_secret=GOOGLE_OAUTH_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )


def get_enabled_providers() -> list[str]:
    return sorted(_clients.keys())


def get_oauth_client(provider: str):
    return _clients.get(provider)


def _extract_identity(provider: str, token: dict, oauth_client) -> tuple[str, str]:
    userinfo = token.get("userinfo")

    if not userinfo:
        try:
            userinfo = oauth_client.userinfo(token=token)
        except Exception:
            userinfo = {}

    if provider == "microsoft" and not userinfo:
        try:
            resp = oauth_client.get("https://graph.microsoft.com/v1.0/me", token=token, timeout=10)
            if resp.ok:
                userinfo = resp.json()
        except Exception:
            userinfo = {}

    if not isinstance(userinfo, dict):
        userinfo = {}

    email = _normalize_email(
        userinfo.get("email")
        or userinfo.get("preferred_username")
        or userinfo.get("upn")
        or userinfo.get("userPrincipalName")
        or userinfo.get("mail")
    )
    name = (userinfo.get("name") or "").strip()

    if not email:
        raise ValueError("Không lấy được email từ nhà cung cấp đăng nhập")

    return email, name


def upsert_user_from_oauth(provider: str, token: dict, oauth_client) -> dict:
    email, name = _extract_identity(provider, token, oauth_client)

    with _db_lock:
        db = _read_db()
        _ensure_admin_seed(db)
        users = db["users"]

        user = next((u for u in users if _normalize_email(u.get("email")) == email), None)
        now = _now_iso()

        if user is None:
            is_admin = email in ADMIN_EMAILS
            user = {
                "id": str(uuid.uuid4()),
                "email": email,
                "name": name or email.split("@")[0],
                "provider": provider,
                "role": "admin" if is_admin else "user",
                "approved": True if is_admin else False,
                "created_at": now,
                "last_login_at": now,
            }
            users.append(user)
        else:
            if email in ADMIN_EMAILS:
                user["role"] = "admin"
                user["approved"] = True
            if name:
                user["name"] = name
            user["provider"] = provider
            user["last_login_at"] = now

        _write_db(db)
        return _public_user(user)


def list_users() -> list[dict]:
    with _db_lock:
        db = _read_db()
        if _ensure_admin_seed(db):
            _write_db(db)
        return [_public_user(u) for u in db.get("users", [])]


def set_session_user(user: dict) -> None:
    session["current_user"] = {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name") or user.get("email"),
        "provider": user.get("provider", ""),
        "role": user.get("role", "user"),
        "approved": bool(user.get("approved", False)),
    }


def clear_session_user() -> None:
    session.pop("current_user", None)


def get_session_user() -> dict | None:
    session_user = session.get("current_user")
    if not isinstance(session_user, dict) or not session_user.get("id"):
        return None

    # Try to refresh from DB to catch real-time approvals/role changes,
    # but use a timeout to avoid blocking requests when the lock is held
    # by a long-running operation (e.g. slow disk I/O, OneDrive sync).
    try:
        acquired = _db_lock.acquire(timeout=2)
        if acquired:
            try:
                db = _read_db()
                user = next((u for u in db["users"] if u.get("id") == session_user["id"]), None)
                if user:
                    updated = _public_user(user)
                    # Sync session with latest DB state
                    set_session_user(updated)
                    return updated
            finally:
                _db_lock.release()
    except Exception:
        pass

    # Fallback: return session data as-is (no DB refresh)
    return {
        "id": session_user.get("id"),
        "email": session_user.get("email"),
        "name": session_user.get("name"),
        "provider": session_user.get("provider", ""),
        "role": session_user.get("role", "user"),
        "approved": bool(session_user.get("approved", False)),
    }


def add_user_by_admin(email: str, name: str = "", approved: bool = True) -> dict:
    email = _normalize_email(email)
    if not email:
        raise ValueError("Email không hợp lệ")

    with _db_lock:
        db = _read_db()
        _ensure_admin_seed(db)
        users = db["users"]

        existing = next((u for u in users if _normalize_email(u.get("email")) == email), None)
        if existing:
            if name:
                existing["name"] = name
            existing["approved"] = bool(approved) or existing.get("role") == "admin"
            _write_db(db)
            return _public_user(existing)

        is_admin = email in ADMIN_EMAILS
        user = {
            "id": str(uuid.uuid4()),
            "email": email,
            "name": (name or email.split("@")[0]).strip(),
            "provider": "manual",
            "role": "admin" if is_admin else "user",
            "approved": True if is_admin else bool(approved),
            "created_at": _now_iso(),
            "last_login_at": None,
        }
        users.append(user)
        _write_db(db)
        return _public_user(user)


def approve_user(user_id: str) -> dict:
    with _db_lock:
        db = _read_db()
        _ensure_admin_seed(db)
        user = next((u for u in db["users"] if u.get("id") == user_id), None)
        if not user:
            raise ValueError("Không tìm thấy user")
        user["approved"] = True
        _write_db(db)
        return _public_user(user)


def delete_user(user_id: str) -> None:
    with _db_lock:
        db = _read_db()
        _ensure_admin_seed(db)
        users = db["users"]

        idx = next((i for i, u in enumerate(users) if u.get("id") == user_id), None)
        if idx is None:
            raise ValueError("Không tìm thấy user")

        target = users[idx]
        if target.get("role") == "admin":
            admins = [u for u in users if u.get("role") == "admin"]
            if len(admins) <= 1:
                raise ValueError("Không thể xóa admin cuối cùng")

        users.pop(idx)
        _write_db(db)


def update_user_role(user_id: str, new_role: str) -> dict:
    if new_role not in ["admin", "user"]:
        raise ValueError("Role không hợp lệ. Chỉ chấp nhận 'admin' hoặc 'user'.")

    with _db_lock:
        db = _read_db()
        _ensure_admin_seed(db)
        user = next((u for u in db["users"] if u.get("id") == user_id), None)
        if not user:
            raise ValueError("Không tìm thấy user")

        # Ngăn chặn việc tự hạ quyền của chính mình nếu là admin duy nhất
        if user["role"] == "admin" and new_role == "user":
            admins = [u for u in db["users"] if u.get("role") == "admin"]
            if len(admins) <= 1:
                raise ValueError("Không thể hạ quyền admin cuối cùng")

        user["role"] = new_role
        _write_db(db)
        return _public_user(user)
