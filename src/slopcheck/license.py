"""Zero-dependency offline licensing client backed by Polar.sh and a 14-day grace cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
from typing import Any
import urllib.error
import urllib.request
import uuid

DEFAULT_API_BASE = "https://api.polar.sh/v1/customer-portal/license-keys"
DEFAULT_ORG_ID = "slopcheck"
OFFLINE_GRACE_DAYS = 14

_SIGNED_FIELDS = (
    "license_key",
    "activation_id",
    "status",
    "expires_at",
    "activated_at",
    "last_verified_at",
    "machine_fingerprint",
)


class LicenseError(Exception):
    """Raised when license activation fails due to input, HTTP, or network errors."""


@dataclass(frozen=True)
class LicenseStatus:
    is_pro: bool
    reason: str
    expires_at: str | None = None


def _get_api_base() -> str:
    value = os.environ.get("SLOPCHECK_POLAR_API_URL", "").strip()
    return (value or DEFAULT_API_BASE).rstrip("/")


def _get_org_id() -> str:
    value = os.environ.get("SLOPCHECK_POLAR_ORG_ID", "").strip()
    return value or DEFAULT_ORG_ID


def get_license_cache_path(cache_dir: str | Path | None = None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir) / "license.json"
    slopcheck_home = os.environ.get("SLOPCHECK_HOME", "").strip()
    if slopcheck_home:
        return Path(slopcheck_home) / "license.json"
    return Path.home() / ".slopcheck" / "license.json"


def compute_machine_fingerprint() -> str:
    raw = f"{platform.system()}:{platform.node()}:{uuid.getnode()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sign_payload(payload: dict[str, Any], fingerprint: str) -> str:
    # Bind the HMAC key to the host fingerprint so copied or edited caches fail validation.
    signing_key = hashlib.sha256(
        f"slopcheck-license-v1:{fingerprint}".encode("utf-8")
    ).digest()
    signed_body = {field: payload.get(field) for field in _SIGNED_FIELDS}
    canonical = json.dumps(signed_body, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hmac.new(signing_key, canonical, hashlib.sha256).hexdigest()


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _parse_utc_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_expired(expires_at: str | None, current_utc: datetime) -> bool:
    if expires_at is None:
        return False
    parsed = _parse_utc_datetime(expires_at)
    if parsed is None:
        return True
    return parsed <= current_utc


def _post_json(url: str, body: dict[str, Any], timeout: float) -> dict[str, Any]:
    encoded = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "slopcheck-cli",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object in response")
    return parsed


def _extract_error_detail(err: urllib.error.HTTPError) -> str:
    try:
        raw = err.read().decode("utf-8", errors="replace")
    except OSError:
        raw = ""
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                detail = data.get("detail") or data.get("error") or data.get("message")
                if isinstance(detail, str) and detail.strip():
                    return detail.strip()
                if isinstance(detail, list) and detail:
                    first = detail[0]
                    if isinstance(first, dict) and isinstance(first.get("msg"), str):
                        return first["msg"].strip()
                    return str(first)
        except json.JSONDecodeError:
            if raw.strip():
                return raw.strip()
    return str(err.reason or f"HTTP {err.code}")


def _extract_status_and_expiry(
    data: dict[str, Any],
    default_expires_at: str | None = None,
) -> tuple[str | None, str | None]:
    nested = data.get("license_key")
    if isinstance(nested, dict):
        status = nested.get("status") if "status" in nested else data.get("status")
        if "expires_at" in nested:
            expires_at = nested.get("expires_at")
        elif "expires_at" in data:
            expires_at = data.get("expires_at")
        else:
            expires_at = default_expires_at
    else:
        status = data.get("status")
        expires_at = data["expires_at"] if "expires_at" in data else default_expires_at

    return (
        status if isinstance(status, str) else None,
        expires_at if isinstance(expires_at, str) or expires_at is None else None,
    )


def _write_signed_cache(cache_path: Path, payload: dict[str, Any]) -> None:
    fingerprint = payload["machine_fingerprint"]
    signed = {field: payload.get(field) for field in _SIGNED_FIELDS}
    signed["signature"] = _sign_payload(signed, fingerprint)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(signed, indent=2) + "\n", encoding="utf-8")


def _load_verified_cache(cache_path: Path) -> dict[str, Any] | None:
    try:
        raw = cache_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(data, dict):
        return None

    required_str_fields = (
        "license_key",
        "activation_id",
        "status",
        "activated_at",
        "last_verified_at",
        "machine_fingerprint",
        "signature",
    )
    for field in required_str_fields:
        if not isinstance(data.get(field), str) or not data[field].strip():
            return None

    expires_at = data.get("expires_at")
    if expires_at is not None and _parse_utc_datetime(expires_at) is None:
        return None

    if _parse_utc_datetime(data["activated_at"]) is None:
        return None
    if _parse_utc_datetime(data["last_verified_at"]) is None:
        return None

    current_fingerprint = compute_machine_fingerprint()
    if data["machine_fingerprint"] != current_fingerprint:
        return None

    expected_sig = _sign_payload(data, current_fingerprint)
    if not hmac.compare_digest(expected_sig, data["signature"]):
        return None

    return data


def activate_license(
    license_key: str,
    cache_dir: str | Path | None = None,
    timeout: float = 10.0,
) -> LicenseStatus:
    """Activate a Polar.sh license key and persist a machine-bound offline cache."""
    key = license_key.strip()
    if not key:
        raise LicenseError("License key must not be empty.")

    url = f"{_get_api_base()}/activate"
    body = {
        "key": key,
        "organization_id": _get_org_id(),
        "label": platform.node() or "slopcheck-cli",
    }

    try:
        data = _post_json(url, body, timeout=timeout)
    except urllib.error.HTTPError as err:
        detail = _extract_error_detail(err)
        raise LicenseError(
            f"License activation failed (HTTP {err.code}): {detail}"
        ) from err
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise LicenseError(
            f"Offline or network error while activating license: {err}"
        ) from err
    except (json.JSONDecodeError, ValueError) as err:
        raise LicenseError(
            f"Invalid response from license server: {err}"
        ) from err

    activation_id = data.get("id")
    if not isinstance(activation_id, str) or not activation_id.strip():
        raise LicenseError("License activation response missing activation id.")

    status, expires_at = _extract_status_and_expiry(data)
    if status != "granted":
        raise LicenseError(f"License key is not active (status: {status!r}).")

    current_utc = _utc_now()
    if _is_expired(expires_at, current_utc):
        raise LicenseError(f"License key expired at {expires_at}.")

    timestamp = current_utc.isoformat()
    payload = {
        "license_key": key,
        "activation_id": activation_id.strip(),
        "status": "granted",
        "expires_at": expires_at,
        "activated_at": timestamp,
        "last_verified_at": timestamp,
        "machine_fingerprint": compute_machine_fingerprint(),
    }

    cache_path = get_license_cache_path(cache_dir)
    try:
        _write_signed_cache(cache_path, payload)
    except OSError as err:
        raise LicenseError(f"Failed to write license cache '{cache_path}': {err}") from err

    return LicenseStatus(is_pro=True, reason="activated", expires_at=expires_at)


def check_pro_license(
    cache_dir: str | Path | None = None,
    now: datetime | None = None,
    timeout: float = 5.0,
) -> LicenseStatus:
    """Verify Pro entitlement locally via 14-day grace cache, revalidating only when due."""
    cache_path = get_license_cache_path(cache_dir)
    if not cache_path.exists():
        return LicenseStatus(is_pro=False, reason="not_activated")

    payload = _load_verified_cache(cache_path)
    if payload is None:
        return LicenseStatus(is_pro=False, reason="invalid_cache")

    current_utc = _utc_now(now)
    cached_expiry = payload.get("expires_at")
    if payload["status"] != "granted" or _is_expired(cached_expiry, current_utc):
        return LicenseStatus(
            is_pro=False,
            reason="expired_or_revoked",
            expires_at=cached_expiry,
        )

    last_verified = _parse_utc_datetime(payload["last_verified_at"])
    if last_verified is None:
        return LicenseStatus(is_pro=False, reason="invalid_cache")

    if (current_utc - last_verified) <= timedelta(days=OFFLINE_GRACE_DAYS):
        return LicenseStatus(
            is_pro=True,
            reason="active_cached",
            expires_at=cached_expiry,
        )

    url = f"{_get_api_base()}/validate"
    body = {
        "key": payload["license_key"],
        "organization_id": _get_org_id(),
        "activation_id": payload["activation_id"],
    }

    try:
        data = _post_json(url, body, timeout=timeout)
    except urllib.error.HTTPError as err:
        if err.code in (401, 403, 404, 422):
            invalidated = dict(payload)
            invalidated["status"] = "revoked"
            try:
                _write_signed_cache(cache_path, invalidated)
            except OSError:
                pass
            return LicenseStatus(
                is_pro=False,
                reason="expired_or_revoked",
                expires_at=cached_expiry,
            )
        return LicenseStatus(
            is_pro=False,
            reason="grace_period_expired",
            expires_at=cached_expiry,
        )
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return LicenseStatus(
            is_pro=False,
            reason="grace_period_expired",
            expires_at=cached_expiry,
        )

    new_status, new_expiry = _extract_status_and_expiry(
        data, default_expires_at=cached_expiry
    )
    if new_status != "granted" or _is_expired(new_expiry, current_utc):
        invalidated = dict(payload)
        invalidated["status"] = new_status or "revoked"
        invalidated["expires_at"] = new_expiry
        try:
            _write_signed_cache(cache_path, invalidated)
        except OSError:
            pass
        return LicenseStatus(
            is_pro=False,
            reason="expired_or_revoked",
            expires_at=new_expiry,
        )

    refreshed = dict(payload)
    refreshed["status"] = "granted"
    refreshed["expires_at"] = new_expiry
    refreshed["last_verified_at"] = current_utc.isoformat()
    try:
        _write_signed_cache(cache_path, refreshed)
    except OSError:
        pass

    return LicenseStatus(
        is_pro=True,
        reason="revalidated",
        expires_at=new_expiry,
    )


def deactivate_local_license(cache_dir: str | Path | None = None) -> bool:
    """Remove the local license cache file if it exists."""
    cache_path = get_license_cache_path(cache_dir)
    if not cache_path.exists():
        return False
    cache_path.unlink()
    return True
