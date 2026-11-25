import base64
import os


def _key(env: str, default_seed: bytes) -> bytes:
    """Read a base64 key from env; fall back to a fixed DEV-ONLY key."""
    raw = os.getenv(env)
    if raw:
        return base64.b64decode(raw)
    return (default_seed * 32)[:32]


DATABASE_URL = os.getenv("SAFEEXAM_DATABASE_URL", "sqlite:///./dev.db")
# 32-byte AES-256 key protecting raw question banks at rest (later: wrapped by Vault/HSM).
MASTER_KEY = _key("SAFEEXAM_MASTER_KEY", b"dev-master-key-DO-NOT-USE-IN-PROD")
# Key for deriving faculty pseudonyms (HMAC), kept separate from the encryption key.
PSEUDONYM_KEY = _key("SAFEEXAM_PSEUDONYM_KEY", b"dev-pseudonym-key-DO-NOT-USE")
JWT_SECRET = os.getenv("SAFEEXAM_JWT_SECRET", "dev-jwt-secret-change-me-please-32b+")
JWT_TTL_MINUTES = int(os.getenv("SAFEEXAM_JWT_TTL_MINUTES", "60"))

# Comma-separated emails allowed to call /pipeline admin endpoints.
ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("SAFEEXAM_ADMIN_EMAILS", "").split(",") if e.strip()}
# Cosine similarity at/above which a question is tagged as a near-duplicate.
NEARDUP_THRESHOLD = float(os.getenv("SAFEEXAM_NEARDUP_THRESHOLD", "0.85"))

# Comma-separated emails allowed to review (blind panel). Admins act as SME moderators.
REVIEWER_EMAILS = {e.strip().lower() for e in os.getenv("SAFEEXAM_REVIEWER_EMAILS", "").split(",") if e.strip()}
REVIEWS_REQUIRED = int(os.getenv("SAFEEXAM_REVIEWS_REQUIRED", "2"))   # independent reviews per question
MIN_QUALITY = float(os.getenv("SAFEEXAM_MIN_QUALITY", "3.0"))         # mean 1-5 score needed to pass
