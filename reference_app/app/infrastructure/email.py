from __future__ import annotations

import httpx

from ..application.auth.ports import EmailSenderPort


class SendGridEmailSender(EmailSenderPort):
    def __init__(
        self,
        api_key: str,
        from_email: str = "fuji@mg.fuji.io.vn",
        from_name: str = "FUJI",
    ) -> None:
        self.api_key = api_key
        self.from_email = from_email
        self.from_name = from_name

    def send_otp_email(
        self, to_email: str, otp_code: str, purpose: str = "verify_email",
    ) -> None:
        if not self.api_key:
            return

        subject = "Interviewly - Mã xác thực OTP của bạn"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 24px; border: 1px solid #eaeaea; border-radius: 8px;">
            <h2 style="color: #4F46E5; margin-bottom: 16px;">Interviewly</h2>
            <p>Xin chào,</p>
            <p>Mã xác thực OTP của bạn cho mục đích <strong>{purpose}</strong> là:</p>
            <div style="background-color: #F3F4F6; padding: 16px; font-size: 28px; letter-spacing: 6px; font-weight: bold; text-align: center; color: #111827; border-radius: 6px; margin: 20px 0;">
                {otp_code}
            </div>
            <p style="color: #6B7280; font-size: 14px;">Mã này có hiệu lực trong vòng 10 phút. Vui lòng không chia sẻ mã này cho bất kỳ ai.</p>
        </div>
        """
        payload = {
            "personalizations": [
                {
                    "to": [{"email": to_email}],
                    "subject": subject,
                }
            ],
            "from": {
                "email": self.from_email,
                "name": self.from_name,
            },
            "content": [
                {
                    "type": "text/html",
                    "value": html_content,
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers=headers,
                    json=payload,
                )
        except Exception:
            pass
