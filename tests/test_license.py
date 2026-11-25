"""Unit tests for the zero-dependency offline licensing engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import urllib.error
from unittest.mock import patch

import pytest

from slopcheck.license import (
    LicenseError,
    LicenseStatus,
    OFFLINE_GRACE_DAYS,
    activate_license,
    check_pro_license,
    compute_machine_fingerprint,
    deactivate_local_license,
    get_license_cache_path,
)


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_http_error(code: int, body: dict | str, reason: str = "Error") -> urllib.error.HTTPError:
    raw = json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
    return urllib.error.HTTPError(
        url="https://api.polar.sh/v1/customer-portal/license-keys/activate",
        code=code,
        msg=reason,
        hdrs=None,
        fp=io.BytesIO(raw),
    )


def _valid_activation_payload(
    activation_id: str = "act_12345",
    status: str = "granted",
    expires_at: str | None = None,
) -> dict:
    return {
        "id": activation_id,
        "license_key": {
            "status": status,
            "expires_at": expires_at,
        },
    }


class TestCachePathAndDeactivation:
    def test_missing_cache_returns_not_activated(self, tmp_path: Path):
        status = check_pro_license(cache_dir=tmp_path)

        assert status == LicenseStatus(is_pro=False, reason="not_activated", expires_at=None)

    def test_slopcheck_home_env_controls_default_cache_path(
        self, tmp_path: Path, monkeypatch
    ):
        monkeypatch.setenv("SLOPCHECK_HOME", str(tmp_path / "custom_home"))
        assert get_license_cache_path() == tmp_path / "custom_home" / "license.json"

    def test_deactivate_local_license(self, tmp_path: Path):
        assert deactivate_local_license(cache_dir=tmp_path) is False

        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-TEST-KEY", cache_dir=tmp_path)

        assert (tmp_path / "license.json").exists()
        assert deactivate_local_license(cache_dir=tmp_path) is True
        assert not (tmp_path / "license.json").exists()
        assert deactivate_local_license(cache_dir=tmp_path) is False


class TestActivateLicense:
    def test_successful_activation_writes_signed_cache(self, tmp_path: Path):
        future_expiry = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(
                _valid_activation_payload(expires_at=future_expiry)
            ),
        ) as mock_urlopen:
            status = activate_license("  SLOP-PRO-1234  ", cache_dir=tmp_path)

        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args.args[0]
        assert req.full_url.endswith("/activate")
        sent_body = json.loads(req.data.decode("utf-8"))
        assert sent_body["key"] == "SLOP-PRO-1234"
        assert sent_body["organization_id"] == "slopcheck"

        assert status == LicenseStatus(
            is_pro=True, reason="activated", expires_at=future_expiry
        )

        cache_file = tmp_path / "license.json"
        assert cache_file.exists()
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        assert cached["license_key"] == "SLOP-PRO-1234"
        assert cached["activation_id"] == "act_12345"
        assert cached["status"] == "granted"
        assert cached["machine_fingerprint"] == compute_machine_fingerprint()
        assert isinstance(cached["signature"], str) and len(cached["signature"]) == 64

    def test_empty_license_key_raises_license_error(self, tmp_path: Path):
        with pytest.raises(LicenseError, match="must not be empty"):
            activate_license("   ", cache_dir=tmp_path)

    @pytest.mark.parametrize("code", [404, 422])
    def test_http_error_raises_clear_license_error(self, tmp_path: Path, code: int):
        err = _make_http_error(code, {"detail": "License key activation limit reached"})
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(LicenseError, match="activation limit reached"):
                activate_license("SLOP-BAD-KEY", cache_dir=tmp_path)

        assert not (tmp_path / "license.json").exists()

    def test_network_error_raises_clear_license_error(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Name or service not known"),
        ):
            with pytest.raises(LicenseError, match="Offline or network error"):
                activate_license("SLOP-OFFLINE", cache_dir=tmp_path)

    def test_already_expired_key_raises_license_error(self, tmp_path: Path):
        past_expiry = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(
                _valid_activation_payload(expires_at=past_expiry)
            ),
        ):
            with pytest.raises(LicenseError, match="expired"):
                activate_license("SLOP-EXPIRED", cache_dir=tmp_path)


class TestCheckProLicenseOfflineAndGrace:
    def test_within_14_day_grace_makes_zero_network_calls(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-GRACE-KEY", cache_dir=tmp_path)

        cached = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
        verified_at = datetime.fromisoformat(cached["last_verified_at"])
        day_13 = verified_at + timedelta(days=OFFLINE_GRACE_DAYS - 1)

        with patch("urllib.request.urlopen") as mock_urlopen:
            status = check_pro_license(cache_dir=tmp_path, now=day_13)

        mock_urlopen.assert_not_called()
        assert status == LicenseStatus(is_pro=True, reason="active_cached", expires_at=None)

    def test_tampered_cache_field_returns_invalid_cache(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-TAMPER", cache_dir=tmp_path)

        cache_file = tmp_path / "license.json"
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        data["last_verified_at"] = "2099-01-01T00:00:00+00:00"
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        status = check_pro_license(cache_dir=tmp_path)
        assert status == LicenseStatus(is_pro=False, reason="invalid_cache")

    def test_mismatched_machine_fingerprint_returns_invalid_cache(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-COPY", cache_dir=tmp_path)

        cache_file = tmp_path / "license.json"
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        data["machine_fingerprint"] = "0" * 64
        cache_file.write_text(json.dumps(data), encoding="utf-8")

        status = check_pro_license(cache_dir=tmp_path)
        assert status == LicenseStatus(is_pro=False, reason="invalid_cache")

    def test_after_14_days_with_network_revalidates_and_updates_cache(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-REVAL", cache_dir=tmp_path)

        cache_file = tmp_path / "license.json"
        initial = json.loads(cache_file.read_text(encoding="utf-8"))
        day_15 = datetime.fromisoformat(initial["last_verified_at"]) + timedelta(
            days=OFFLINE_GRACE_DAYS + 1
        )

        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"status": "granted", "expires_at": None}),
        ) as mock_urlopen:
            status = check_pro_license(cache_dir=tmp_path, now=day_15)

        assert mock_urlopen.call_count == 1
        req = mock_urlopen.call_args.args[0]
        assert req.full_url.endswith("/validate")
        sent = json.loads(req.data.decode("utf-8"))
        assert sent == {
            "key": "SLOP-REVAL",
            "organization_id": "slopcheck",
            "activation_id": "act_12345",
        }

        assert status == LicenseStatus(is_pro=True, reason="revalidated", expires_at=None)
        updated = json.loads(cache_file.read_text(encoding="utf-8"))
        assert updated["last_verified_at"] == day_15.isoformat()

        # Subsequent offline check on day 16 uses refreshed timestamp without network calls
        day_16 = day_15 + timedelta(days=1)
        with patch("urllib.request.urlopen") as mock_urlopen_again:
            cached_again = check_pro_license(cache_dir=tmp_path, now=day_16)
        mock_urlopen_again.assert_not_called()
        assert cached_again.is_pro is True
        assert cached_again.reason == "active_cached"

    def test_after_14_days_offline_returns_grace_period_expired(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-OFFLINE-DAY15", cache_dir=tmp_path)

        initial = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
        day_15 = datetime.fromisoformat(initial["last_verified_at"]) + timedelta(
            days=OFFLINE_GRACE_DAYS + 1
        )

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("offline"),
        ):
            status = check_pro_license(cache_dir=tmp_path, now=day_15)

        assert status == LicenseStatus(
            is_pro=False, reason="grace_period_expired", expires_at=None
        )

    def test_after_14_days_revoked_updates_cache_and_returns_expired_or_revoked(
        self, tmp_path: Path
    ):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-REVOKED", cache_dir=tmp_path)

        initial = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
        day_15 = datetime.fromisoformat(initial["last_verified_at"]) + timedelta(
            days=OFFLINE_GRACE_DAYS + 1
        )

        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"status": "revoked", "expires_at": None}),
        ):
            status = check_pro_license(cache_dir=tmp_path, now=day_15)

        assert status == LicenseStatus(
            is_pro=False, reason="expired_or_revoked", expires_at=None
        )

        # Even if checked offline afterwards, updated cache remains revoked
        with patch("urllib.request.urlopen") as mock_urlopen:
            follow_up = check_pro_license(cache_dir=tmp_path, now=day_15)
        mock_urlopen.assert_not_called()
        assert follow_up == LicenseStatus(
            is_pro=False, reason="expired_or_revoked", expires_at=None
        )

    def test_after_14_days_http_404_returns_expired_or_revoked(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-404", cache_dir=tmp_path)

        initial = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
        day_15 = datetime.fromisoformat(initial["last_verified_at"]) + timedelta(
            days=OFFLINE_GRACE_DAYS + 1
        )

        err = _make_http_error(404, {"detail": "License key not found"})
        with patch("urllib.request.urlopen", side_effect=err):
            status = check_pro_license(cache_dir=tmp_path, now=day_15)

        assert status == LicenseStatus(
            is_pro=False, reason="expired_or_revoked", expires_at=None
        )

    def test_corrupt_json_returns_invalid_cache(self, tmp_path: Path):
        (tmp_path / "license.json").write_text("{corrupt", encoding="utf-8")
        status = check_pro_license(cache_dir=tmp_path)
        assert status == LicenseStatus(is_pro=False, reason="invalid_cache")

    def test_after_14_days_5xx_returns_grace_period_expired(self, tmp_path: Path):
        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ):
            activate_license("SLOP-503", cache_dir=tmp_path)

        initial = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
        day_15 = datetime.fromisoformat(initial["last_verified_at"]) + timedelta(
            days=OFFLINE_GRACE_DAYS + 1
        )

        err = _make_http_error(503, {"detail": "Service unavailable"})
        with patch("urllib.request.urlopen", side_effect=err):
            status = check_pro_license(cache_dir=tmp_path, now=day_15)

        assert status == LicenseStatus(
            is_pro=False, reason="grace_period_expired", expires_at=None
        )

    def test_env_overrides_for_api_url_and_org_id(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("SLOPCHECK_POLAR_API_URL", "https://custom.example/keys/")
        monkeypatch.setenv("SLOPCHECK_POLAR_ORG_ID", "acme-org")

        with patch(
            "urllib.request.urlopen",
            return_value=_FakeHTTPResponse(_valid_activation_payload()),
        ) as mock_urlopen:
            activate_license("SLOP-ENV", cache_dir=tmp_path)

        req = mock_urlopen.call_args.args[0]
        assert req.full_url == "https://custom.example/keys/activate"
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["organization_id"] == "acme-org"
