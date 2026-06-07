import smtplib
import threading
import requests as _requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import config


# ============================================================
# Gửi qua Microsoft Graph API (không cần SMTP credentials)
# ============================================================

def send_mail_via_graph(access_token: str, subject: str, body_html: str, recipients: list, sender_email: str = None) -> bool:
    """
    Gửi email qua Microsoft Graph API /me/sendMail.
    Email gửi từ chính tài khoản của user đang đăng nhập.
    Trả về True nếu thành công.
    """
    if not access_token or not recipients:
        return False

    clean_recipients = [r.strip() for r in recipients if r and r.strip()]
    if not clean_recipients:
        return False

    to_recipients = [{"emailAddress": {"address": r}} for r in clean_recipients]

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html,
            },
            "toRecipients": to_recipients,
        },
        "saveToSentItems": True,
    }

    if sender_email:
        payload["message"]["from"] = {
            "emailAddress": {
                "name": "RMC Assistant",
                "address": sender_email.strip()
            }
        }

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = _requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            json=payload,
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 202:
            print(f"[GraphMail] Gửi thành công đến: {', '.join(clean_recipients)}")
            return True
        else:
            print(f"[GraphMail] Lỗi HTTP {resp.status_code}: {resp.text[:300]}")
            return False
    except Exception as e:
        print(f"[GraphMail] Exception: {e}")
        return False


def send_mail_via_graph_async(access_token: str, subject: str, body_html: str,
                               recipients: list,
                               sender_email: str = None,
                               refresh_token: str = None) -> None:
    """
    Gửi email qua Graph API trong background thread.
    Nếu access_token hết hạn và có refresh_token, tự động làm mới.
    """
    def _send():
        token = access_token
        # Thử gửi với token hiện tại
        ok = send_mail_via_graph(token, subject, body_html, recipients, sender_email=sender_email)
        if not ok and refresh_token:
            # Token hết hạn → làm mới
            print("[GraphMail] access_token hết hạn, đang làm mới bằng refresh_token...")
            try:
                from auth.user_auth import refresh_ms_access_token, save_ms_refresh_token_for_user
                new_token, new_refresh = refresh_ms_access_token(refresh_token)
                if new_token:
                    # Cập nhật refresh_token mới vào users.json nếu Microsoft trả về refresh_token mới
                    if new_refresh and new_refresh != refresh_token and sender_email:
                        import json
                        from config import USERS_DB_FILE
                        try:
                            with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                                db = json.load(f)
                            user = next((u for u in db.get("users", [])
                                         if u.get("email", "").lower() == sender_email.lower()), None)
                            if user:
                                save_ms_refresh_token_for_user(user["id"], new_refresh)
                        except Exception as e2:
                            print(f"[GraphMail] Không thể cập nhật refresh_token: {e2}")
                    send_mail_via_graph(new_token, subject, body_html, recipients, sender_email=sender_email)
                else:
                    print("[GraphMail] Làm mới token thất bại. Email không được gửi.")
            except Exception as e:
                print(f"[GraphMail] Lỗi khi làm mới token: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ============================================================
# Gửi qua SMTP (fallback nếu không có MS token)
# ============================================================

def send_email_async(subject: str, body_html: str, recipients: list):
    """
    Gửi email bất đồng bộ qua SMTP (không làm block luồng Scheduler chính).
    """
    if not config.SMTP_HOST:
        print("[EmailService] Bỏ qua gửi email: Chưa cấu hình SMTP_HOST.")
        return

    if not recipients:
        print("[EmailService] Bỏ qua gửi email: Danh sách người nhận trống.")
        return

    clean_recipients = [r.strip() for r in recipients if r and r.strip()]
    if not clean_recipients:
        return

    def _send():
        try:
            from email.utils import formataddr
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            sender_addr = config.SMTP_SENDER or config.SMTP_USER
            msg["From"] = formataddr(("RMC Assistant", sender_addr))
            msg["To"] = ", ".join(clean_recipients)

            html_part = MIMEText(body_html, "html", "utf-8")
            msg.attach(html_part)

            secure_mode = config.SMTP_SECURE
            if secure_mode == "ssl":
                server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
            else:
                server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10)
                if secure_mode == "tls":
                    server.starttls()

            if config.SMTP_USER and config.SMTP_PASSWORD:
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)

            server.sendmail(sender_addr, clean_recipients, msg.as_string())
            server.quit()
            print(f"[EmailService] Đã gửi email thành công đến: {', '.join(clean_recipients)}")

        except Exception as e:
            print(f"[EmailService] LỖI khi gửi email SMTP: {e}")

    threading.Thread(target=_send, daemon=True).start()


# ============================================================
# Hàm build HTML body email
# ============================================================

def _build_reminder_html(keyword: str, content: str, time_str: str) -> str:
    import re
    import datetime
    keyword_clean = re.sub(r'^\[.*?\]\s*', '', keyword)
    date_str = datetime.datetime.now().strftime("%d/%m/%Y")
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 15px;
            line-height: 1.6;
            color: #0f172a;
            margin: 0;
            padding: 20px;
            background-color: #ffffff;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
        }}
        .content-box {{
            white-space: pre-wrap;
            margin-top: 12px;
            margin-bottom: 24px;
            font-family: inherit;
        }}
        .footer {{
            margin-top: 24px;
            border-top: 1px dashed #cbd5e1;
            padding-top: 16px;
            font-size: 13px;
            color: #64748b;
        }}
    </style>
</head>
<body>
    <div class="container">
        <p style="margin: 0 0 16px 0; font-weight: bold; font-size: 16px;">🔔 {keyword}</p>
        
        <p style="margin: 0 0 16px 0;">Chào Mọi người,</p>
        
        <p style="margin: 0 0 16px 0;">Tôi xin gửi thông tin nhắc lịch từ hệ thống RMC Assistant:</p>
        
        <p style="margin: 0 0 16px 0;">Thời gian: {time_str}, ngày {date_str}</p>
        
        <p style="margin: 0 0 4px 0; font-weight: bold;">Nội dung chính:</p>
        <div class="content-box">{content}</div>
        
        <p style="margin: 24px 0 0 0;">Trân trọng,<br>
        RMC Assistant</p>
        
        <div class="footer">
            Email này được gửi tự động từ hệ thống RMC Assistant.<br>
            Vui lòng không phản hồi lại email này.
        </div>
    </div>
</body>
</html>
"""


def _build_note_change_html(action: str, note: dict) -> tuple[str, str]:
    """Trả về (subject, body_html) cho email thông báo tạo/sửa Note."""
    stt = note.get("_stt") or note.get("stt", "N/A")
    keyword = note.get("keyword", "")
    content = note.get("content", "")
    times = ", ".join(note.get("times", []))
    days_list = note.get("days", [])
    months_list = note.get("months", [])

    days = "Tất cả" if len(days_list) == 31 else ", ".join(days_list)
    months = "Tất cả" if len(months_list) == 12 else ", ".join(months_list)

    mode = note.get("mode", "Cố định")
    paused = note.get("paused", False)
    status_str = "Tạm dừng" if paused else "Hoạt động"

    action_label = "TẠO MỚI NHẮC NHỞ" if action == "CREATE" else "CẬP NHẬT NHẮC NHỞ"
    subject = f"[RMC Assistant] {action_label}: {keyword}"

    is_update = action == "UPDATE"
    header_color = "linear-gradient(135deg, #3b82f6, #2563eb)" if is_update else "linear-gradient(135deg, #10b981, #059669)"
    border_color = "#3b82f6" if is_update else "#10b981"

    body_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f6f9; color: #333333; margin: 0; padding: 20px; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 8px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); border: 1px solid #e1e8ed; overflow: hidden; }}
        .header {{ background: {header_color}; color: #ffffff; padding: 20px; text-align: center; }}
        .header h2 {{ margin: 0; font-size: 20px; font-weight: 600; }}
        .content {{ padding: 25px 20px; line-height: 1.6; }}
        .info-row {{ display: block; margin-bottom: 12px; border-bottom: 1px solid #f1f5f9; padding-bottom: 12px; }}
        .info-label {{ font-weight: bold; color: #64748b; margin-bottom: 4px; }}
        .info-value {{ color: #0f172a; font-size: 16px; }}
        .message-box {{ background-color: #f8fafc; border-left: 4px solid {border_color}; padding: 15px; border-radius: 4px; margin-top: 20px; font-style: italic; white-space: pre-wrap; color: #1e293b; }}
        .footer {{ background: #f8fafc; color: #64748b; padding: 15px; text-align: center; font-size: 12px; border-top: 1px solid #e2e8f0; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <h2>🔔 {action_label} (STT: #{stt})</h2>
        </div>
        <div class="content">
            <div class="info-row">
                <div class="info-label">Từ khóa:</div>
                <div class="info-value"><strong>{keyword}</strong></div>
            </div>
            <div class="info-row">
                <div class="info-label">Giờ nhắc:</div>
                <div class="info-value">{times}</div>
            </div>
            <div class="info-row">
                <div class="info-label">Ngày nhắc:</div>
                <div class="info-value">{days}</div>
            </div>
            <div class="info-row">
                <div class="info-label">Tháng nhắc:</div>
                <div class="info-value">{months}</div>
            </div>
            <div class="info-row">
                <div class="info-label">Chế độ &amp; Trạng thái:</div>
                <div class="info-value">Chế độ: {mode} | Trạng thái: <strong>{status_str}</strong></div>
            </div>
            <div class="info-row">
                <div class="info-label">Nội dung chi tiết:</div>
                <div class="message-box">{content}</div>
            </div>
        </div>
        <div class="footer">
            Email này được gửi tự động từ hệ thống RMC Assistant.<br>
            Vui lòng không phản hồi lại email này.
        </div>
    </div>
</body>
</html>
"""
    return subject, body_html


# ============================================================
# Public API — dùng từ note.py
# ============================================================

def send_reminder_email(keyword: str, content: str, time_str: str, recipients: list,
                        ms_access_token: str = None, ms_refresh_token: str = None,
                        sender_email: str = None):
    """
    Gửi email nhắc lịch định kỳ.
    Ưu tiên Graph API nếu có token, fallback về SMTP nếu đã cấu hình.
    Khi scheduler gọi: chỉ có refresh_token → tự động đổi sang access_token mới.
    """
    body_html = _build_reminder_html(keyword, content, time_str)
    subject = keyword if keyword.startswith("[") else f"[RMC Assistant] - {keyword}"

    # Nếu không có access_token nhưng có refresh_token → tự động lấy access_token mới
    if not ms_access_token and ms_refresh_token:
        try:
            from auth.user_auth import refresh_ms_access_token, save_ms_refresh_token_for_user
            print(f"[EmailService] Đang lấy access_token mới từ refresh_token cho {sender_email}...")
            new_access, new_refresh = refresh_ms_access_token(ms_refresh_token)
            if new_access:
                ms_access_token = new_access
                print(f"[EmailService] Lấy access_token thành công!")
                # Cập nhật refresh_token mới nếu có
                if new_refresh and new_refresh != ms_refresh_token and sender_email:
                    import json
                    from config import USERS_DB_FILE
                    try:
                        with open(USERS_DB_FILE, "r", encoding="utf-8") as f:
                            db = json.load(f)
                        user = next((u for u in db.get("users", [])
                                     if u.get("email", "").lower() == sender_email.lower()), None)
                        if user:
                            save_ms_refresh_token_for_user(user["id"], new_refresh)
                            print(f"[EmailService] Đã cập nhật refresh_token mới cho {sender_email}")
                    except Exception as e2:
                        print(f"[EmailService] Không thể cập nhật refresh_token: {e2}")
            else:
                print(f"[EmailService] Không thể lấy access_token mới. Kiểm tra refresh_token.")
        except Exception as e:
            print(f"[EmailService] Lỗi khi lấy access_token từ refresh_token: {e}")

    if ms_access_token:
        send_mail_via_graph_async(ms_access_token, subject, body_html, recipients,
                                   sender_email=sender_email, refresh_token=ms_refresh_token)
    elif config.SMTP_HOST and config.SMTP_USER:
        send_email_async(subject, body_html, recipients)
    else:
        print("[EmailService] Không có Graph token và chưa cấu hình SMTP. Bỏ qua gửi email nhắc lịch.")


def send_note_change_email(action: str, note: dict,
                           ms_access_token: str = None,
                           ms_refresh_token: str = None,
                           sender_email: str = None):
    """
    Gửi email thông báo khi tạo mới hoặc cập nhật một note nhắc lịch.
    Ưu tiên Graph API nếu có token, fallback về SMTP nếu đã cấu hình.
    """
    recipients = note.get("emails", [])
    if not recipients:
        return

    subject, body_html = _build_note_change_html(action, note)

    if ms_access_token:
        send_mail_via_graph_async(ms_access_token, subject, body_html, recipients,
                                   sender_email=sender_email, refresh_token=ms_refresh_token)
    elif config.SMTP_HOST and config.SMTP_USER:
        send_email_async(subject, body_html, recipients)
    else:
        print("[EmailService] Không có Graph token và chưa cấu hình SMTP. Bỏ qua gửi email Note.")
