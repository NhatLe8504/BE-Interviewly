from __future__ import annotations

import os
from dataclasses import dataclass


def _load_env_file() -> None:
    for candidate in [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]:
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k:
                                os.environ[k] = v
            except Exception:
                pass


_load_env_file()
from dataclasses import dataclass

API_TITLE = "BE-Interviewly"
API_VERSION = "0.1.0"
API_DESCRIPTION = "BE Interview Coach API."

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://interviewly:interviewly@localhost:5432/interviewly"
)
DEFAULT_JWT_SECRET = "dev-only-secret-change-me-please-set-JWT_SECRET-32-chars-min"
DEFAULT_JWT_EXPIRES_MINUTES = 1440
DEFAULT_GOOGLE_CLIENT_ID = ""
DEFAULT_GOOGLE_CLIENT_SECRET = ""
DEFAULT_SENDGRID_FROM_EMAIL = "fuji@mg.fuji.io.vn"
DEFAULT_SENDGRID_FROM_NAME = "FUJI"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_VNPAY_TMN_CODE = "INTERVIE"
DEFAULT_VNPAY_HASH_SECRET = "SANDBOXSECRETKEY1234567890ABCDEF"
DEFAULT_VNPAY_PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
DEFAULT_VNPAY_RETURN_URL = "http://localhost:3000/subscription/result/success"



# Groq Ultra-Fast LPU Configuration
DEFAULT_GROQ_KEY = "dummy-groq-key-configured-in-env"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# OpenRouter DeepSeek Configuration
DEFAULT_OPENROUTER_KEY = "dummy-openrouter-key-configured-in-env"
DEFAULT_OPENROUTER_MODEL = "deepseek/deepseek-v4-flash-0731"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# xGate Payment Gateway Config
DEFAULT_XGATE_API_KEY = "xgate_86c34581a1efc75cf97ab04f51eae3845030"
DEFAULT_XGATE_API_URL = "https://api.xgate.vn/api/v1/transactions"
DEFAULT_XGATE_RECEIVER_BANK = "mb"
DEFAULT_XGATE_RECEIVER_ACCOUNT = "9394441571"
DEFAULT_XGATE_RECEIVER_NAME = "LE VAN NHAT"


@dataclass(frozen=True)
class Settings:
    database_url: str = DEFAULT_DATABASE_URL
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_expires_minutes: int = DEFAULT_JWT_EXPIRES_MINUTES
    google_client_id: str = DEFAULT_GOOGLE_CLIENT_ID
    google_client_secret: str = DEFAULT_GOOGLE_CLIENT_SECRET
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = DEFAULT_SENDGRID_FROM_EMAIL
    sendgrid_from_name: str = DEFAULT_SENDGRID_FROM_NAME
    openai_api_key: str = ""
    openai_model: str = "deepseek/deepseek-v4-flash-0731:free"
    openai_base_url: str = "https://openrouter.ai/api/v1"
    redis_url: str = DEFAULT_REDIS_URL
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    cloudinary_url: str = ""
    vnpay_tmn_code: str = DEFAULT_VNPAY_TMN_CODE
    vnpay_hash_secret: str = DEFAULT_VNPAY_HASH_SECRET
    vnpay_payment_url: str = DEFAULT_VNPAY_PAYMENT_URL
    vnpay_return_url: str = DEFAULT_VNPAY_RETURN_URL
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    xgate_api_key: str = DEFAULT_XGATE_API_KEY
    xgate_api_url: str = DEFAULT_XGATE_API_URL
    xgate_receiver_bank: str = DEFAULT_XGATE_RECEIVER_BANK
    xgate_receiver_account: str = DEFAULT_XGATE_RECEIVER_ACCOUNT
    xgate_receiver_name: str = DEFAULT_XGATE_RECEIVER_NAME
    pdf_reports_dir: str = "reports"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
            jwt_secret=os.environ.get("JWT_SECRET", DEFAULT_JWT_SECRET),
            jwt_expires_minutes=int(
                os.environ.get(
                    "JWT_EXPIRES_MINUTES", str(DEFAULT_JWT_EXPIRES_MINUTES),
                ),
            ),
            google_client_id=os.environ.get(
                "GOOGLE_CLIENT_ID", DEFAULT_GOOGLE_CLIENT_ID,
            ),
            google_client_secret=os.environ.get(
                "GOOGLE_CLIENT_SECRET", DEFAULT_GOOGLE_CLIENT_SECRET,
            ),
            sendgrid_api_key=os.environ.get("SENDGRID_API_KEY", ""),
            sendgrid_from_email=os.environ.get(
                "SENDGRID_FROM_EMAIL", DEFAULT_SENDGRID_FROM_EMAIL,
            ),
            sendgrid_from_name=os.environ.get(
                "SENDGRID_FROM_NAME", DEFAULT_SENDGRID_FROM_NAME,
            ),
            openai_api_key=(
                os.environ.get("GROQ_KEY")
                or os.environ.get("GROQ_API_KEY")
                or os.environ.get("OPEN_ROUTER_KEY")
                or os.environ.get("OPENROUTER_API_KEY")
                or DEFAULT_GROQ_KEY
            ),
            openai_model=os.environ.get(
                "GROQ_MODEL",
                os.environ.get(
                    "OPENROUTER_MODEL",
                    DEFAULT_GROQ_MODEL if (os.environ.get("GROQ_KEY") or os.environ.get("GROQ_API_KEY") or DEFAULT_GROQ_KEY) else DEFAULT_OPENROUTER_MODEL,
                ),
            ),
            openai_base_url=os.environ.get(
                "GROQ_BASE_URL",
                os.environ.get(
                    "OPENROUTER_BASE_URL",
                    DEFAULT_GROQ_BASE_URL if (os.environ.get("GROQ_KEY") or os.environ.get("GROQ_API_KEY") or DEFAULT_GROQ_KEY) else DEFAULT_OPENROUTER_BASE_URL,
                ),
            ),
            redis_url=os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
            cloudinary_cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
            cloudinary_api_key=os.environ.get("CLOUDINARY_API_KEY", ""),
            cloudinary_api_secret=os.environ.get("CLOUDINARY_API_SECRET", ""),
            cloudinary_url=os.environ.get("CLOUDINARY_URL", ""),
            vnpay_tmn_code=os.environ.get(
                "VNPAY_TMN_CODE", DEFAULT_VNPAY_TMN_CODE,
            ),
            vnpay_hash_secret=os.environ.get(
                "VNPAY_HASH_SECRET", DEFAULT_VNPAY_HASH_SECRET,
            ),
            vnpay_payment_url=os.environ.get(
                "VNPAY_PAYMENT_URL", DEFAULT_VNPAY_PAYMENT_URL,
            ),
            vnpay_return_url=os.environ.get(
                "VNPAY_RETURN_URL", DEFAULT_VNPAY_RETURN_URL,
            ),
            stripe_api_key=os.environ.get("STRIPE_API_KEY", ""),
            stripe_webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            xgate_api_key=os.environ.get("XGATE_API_KEY", DEFAULT_XGATE_API_KEY),
            xgate_api_url=os.environ.get("XGATE_API_URL", DEFAULT_XGATE_API_URL),
            xgate_receiver_bank=os.environ.get("PAYMENT_QR_BANK_CODE", os.environ.get("XGATE_RECEIVER_BANK", DEFAULT_XGATE_RECEIVER_BANK)),
            xgate_receiver_account=os.environ.get("PAYMENT_QR_ACCOUNT_NUMBER", os.environ.get("XGATE_RECEIVER_ACCOUNT", os.environ.get("XGATE_ACCOUNT", DEFAULT_XGATE_RECEIVER_ACCOUNT))),
            xgate_receiver_name=os.environ.get("PAYMENT_QR_ACCOUNT_NAME", os.environ.get("XGATE_RECEIVER_NAME", DEFAULT_XGATE_RECEIVER_NAME)),
            pdf_reports_dir=os.environ.get("PDF_REPORTS_DIR", "reports"),
        )
