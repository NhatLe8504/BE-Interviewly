from __future__ import annotations

import httpx

from ..application.auth.ports import GoogleProfile, GoogleTokenVerifierPort
from ..domain.errors import AuthError


class GoogleOAuthAdapter(GoogleTokenVerifierPort):
    def __init__(self, client_id: str | None = None) -> None:
        self.client_id = client_id

    def verify(self, credential: str) -> GoogleProfile:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": credential},
                )
        except Exception as exc:
            raise AuthError(f"failed to connect to Google OAuth service: {exc}") from exc

        if resp.status_code != 200:
            raise AuthError("invalid or expired Google credential")

        data = resp.json()
        aud = data.get("aud")
        if self.client_id and aud != self.client_id:
            raise AuthError("Google token audience mismatch")

        email = data.get("email")
        if not email:
            raise AuthError("Google token missing email")

        name = data.get("name") or email.partition("@")[0]
        sub = data.get("sub", "")
        picture = data.get("picture")

        return GoogleProfile(
            email=email,
            full_name=name,
            google_id=sub,
            picture_url=picture,
        )
