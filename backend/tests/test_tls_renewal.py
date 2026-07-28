"""TLS auto-renewal: expiry detection, binary resolution, and the renew trigger."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.services import tls_renewal
from app.services.tls_renewal import (
    RENEW_WITHIN_DAYS,
    _days_until_expiry,
    _resolve_bin,
    tls_renewal_loop,
)

DOMAIN = "test-host.tail00000.ts.net"


def _write_cert(cert_dir, days_until_expiry: float) -> None:
    """Write a self-signed cert/key pair to cert_dir expiring days_until_expiry from now."""
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=90))
        .not_valid_after(now + timedelta(days=days_until_expiry))
        .sign(key, hashes.SHA256())
    )
    (cert_dir / f"{DOMAIN}.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (cert_dir / f"{DOMAIN}.key").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


# ── Expiry detection ─────────────────────────────────────────────────────────

def test_days_until_expiry_reads_the_certificate(tmp_path):
    _write_cert(tmp_path, days_until_expiry=45)
    assert _days_until_expiry(tmp_path / f"{DOMAIN}.crt") == pytest.approx(45, abs=0.1)


def test_days_until_expiry_is_negative_for_an_expired_cert(tmp_path):
    """Regression: the age check used to compare st_mtime against the event
    loop's monotonic clock, which is seconds-since-boot rather than epoch
    seconds. That made every cert look impossibly new, so renewal never fired
    and the cert silently lapsed."""
    _write_cert(tmp_path, days_until_expiry=-14)
    days_left = _days_until_expiry(tmp_path / f"{DOMAIN}.crt")
    assert days_left == pytest.approx(-14, abs=0.1)
    assert days_left <= RENEW_WITHIN_DAYS  # i.e. it triggers renewal


def test_days_until_expiry_returns_none_on_garbage(tmp_path):
    bad = tmp_path / f"{DOMAIN}.crt"
    bad.write_text("not a certificate")
    assert _days_until_expiry(bad) is None


# ── Binary resolution ────────────────────────────────────────────────────────

def test_resolve_bin_returns_none_when_missing():
    assert _resolve_bin("definitely-not-a-real-binary-xyz") is None


def test_resolve_bin_falls_back_off_path(monkeypatch, tmp_path):
    """`tailscale` is not on PATH in a macOS app install, and launchd gives the
    backend a minimal PATH, so the fallback locations must be consulted."""
    fake = tmp_path / "tailscale"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setattr(tls_renewal.shutil, "which", lambda _: None)
    monkeypatch.setitem(tls_renewal._BIN_FALLBACKS, "tailscale", (str(fake),))
    assert _resolve_bin("tailscale") == str(fake)


# ── Loop behaviour ───────────────────────────────────────────────────────────

async def _run_one_pass(monkeypatch, cert_dir) -> list[str]:
    """Run tls_renewal_loop for exactly one iteration and report what it did."""
    calls: list[str] = []

    async def fake_renew(domain, cert_path, key_path):
        calls.append("renew")
        return True

    async def fake_reload():
        calls.append("reload")

    async def stop_after_first_pass(_seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(tls_renewal, "_renew_cert", fake_renew)
    monkeypatch.setattr(tls_renewal, "_reload_caddy", fake_reload)
    monkeypatch.setattr(tls_renewal.asyncio, "sleep", stop_after_first_pass)

    await tls_renewal_loop(DOMAIN, str(cert_dir))
    return calls


@pytest.mark.asyncio
async def test_loop_renews_an_expiring_cert_on_the_first_pass(monkeypatch, tmp_path):
    """Checking before sleeping matters: an already-expired cert must be fixed
    at startup, not CHECK_INTERVAL (6h) later."""
    _write_cert(tmp_path, days_until_expiry=-1)
    assert await _run_one_pass(monkeypatch, tmp_path) == ["renew", "reload"]


@pytest.mark.asyncio
async def test_loop_leaves_a_fresh_cert_alone(monkeypatch, tmp_path):
    _write_cert(tmp_path, days_until_expiry=RENEW_WITHIN_DAYS + 10)
    assert await _run_one_pass(monkeypatch, tmp_path) == []


@pytest.mark.asyncio
async def test_loop_survives_a_missing_cert(monkeypatch, tmp_path):
    assert await _run_one_pass(monkeypatch, tmp_path) == []


# ── Config wiring ────────────────────────────────────────────────────────────

def test_relative_cert_dir_resolves_against_the_repo_root(monkeypatch):
    """The backend runs with CWD=backend/, so a bare "./certs" would resolve to
    backend/certs instead of the repo-root certs/ that Caddy mounts."""
    from pathlib import Path

    import app.config as config

    config.get_settings.cache_clear()
    monkeypatch.setenv("TLS_CERT_DIR", "./certs")
    try:
        cert_dir = Path(config.get_settings().tls_cert_dir)
    finally:
        config.get_settings.cache_clear()

    assert cert_dir.is_absolute()
    assert cert_dir == Path(config.__file__).resolve().parents[2] / "certs"


def test_tls_domain_defaults_to_nexus_host(monkeypatch):
    import app.config as config

    config.get_settings.cache_clear()
    monkeypatch.delenv("TLS_DOMAIN", raising=False)
    monkeypatch.setenv("NEXUS_HOST", DOMAIN)
    try:
        assert config.get_settings().tls_domain == DOMAIN
    finally:
        config.get_settings.cache_clear()
