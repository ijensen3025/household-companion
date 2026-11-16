"""Secure, signed IAP identity. No untrusted profile selector can grant authority."""
import os
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException

IAP_KEYS = "https://www.gstatic.com/iap/verify/public_key-jwk"
_jwks = PyJWKClient(IAP_KEYS, cache_jwk_set=True, lifespan=3600)


def expected_audience():
    return os.getenv("IAP_AUDIENCE") or ("/projects/116405340329/locations/us-central1/services/household-companion")


def verified_email(request):
    token = request.headers.get("x-goog-iap-jwt-assertion")
    if not token:
        raise HTTPException(401, "Google sign-in is required")
    try:
        key = _jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["ES256"],
            audience=expected_audience(), issuer="https://cloud.google.com/iap", leeway=30)
        return claims["email"].casefold()
    except Exception:
        raise HTTPException(401, "Could not verify Google sign-in")


def member_for_request(request):
    email = verified_email(request)
    owner = os.getenv("OWNER_EMAIL", "").strip().casefold()
    husband = os.getenv("HUSBAND_EMAIL", "").strip().casefold()
    daughter = os.getenv("DAUGHTER_EMAIL", "").strip().casefold()
    if not owner:
        raise HTTPException(503, "Family identity setup is not yet configured")
    mapping = {owner: "Ida"}
    if husband: mapping[husband] = "Husband"
    if daughter: mapping[daughter] = "Daughter"
    member = mapping.get(email)
    if not member:
        raise HTTPException(403, "This Google account is not registered as a household member")
    return member
