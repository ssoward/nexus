"""Background task: check Tailscale TLS cert expiry, renew before it lapses."""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 6 * 3600  # 6 hours
# Tailscale issues 90-day certs. Renew once the cert has this little left, which
# leaves weeks of retries if Tailscale or the network is briefly unavailable.
RENEW_WITHIN_DAYS = 30

# Neither `tailscale` nor `docker` is on PATH in a macOS GUI-app install, and
# under launchd (macos/*.plist.template sets no PATH) the backend inherits a
# minimal environment. Resolve absolute paths instead of trusting PATH.
_BIN_FALLBACKS = {
    "tailscale": (
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale",
    ),
    "docker": (
        "/Applications/Docker.app/Contents/Resources/bin/docker",
        "/usr/local/bin/docker",
        "/opt/homebrew/bin/docker",
    ),
}


def _resolve_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in _BIN_FALLBACKS.get(name, ()):
        if os.path.exists(candidate):
            return candidate
    return None


def _days_until_expiry(cert_path: Path) -> float | None:
    """Days until the cert's notAfter, or None if it can't be parsed.

    Reads the certificate itself rather than the file mtime: mtime is preserved
    by copy2 and says nothing about the validity window actually issued.
    """
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except Exception as e:
        logger.warning("Could not parse TLS cert %s: %s", cert_path, e)
        return None
    return (cert.not_valid_after_utc - datetime.now(timezone.utc)).total_seconds() / 86400


async def _run(*argv: str) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode or 0, (stderr or stdout).decode(errors="replace").strip()


async def _renew_cert(domain: str, cert_path: Path, key_path: Path) -> bool:
    """Fetch a fresh cert/key pair and move it into place atomically."""
    tailscale = _resolve_bin("tailscale")
    if tailscale is None:
        logger.error(
            "TLS renewal skipped: `tailscale` CLI not found on PATH or in the "
            "usual install locations. Renew manually: tailscale cert %s", domain
        )
        return False

    # Write beside the live files (same filesystem, so os.replace is atomic) so
    # a failed fetch can never leave Caddy serving a half-written cert.
    tmp_cert = cert_path.with_name(cert_path.name + ".new")
    tmp_key = key_path.with_name(key_path.name + ".new")
    rc, err = await _run(
        tailscale, "cert",
        "--cert-file", str(tmp_cert),
        "--key-file", str(tmp_key),
        domain,
    )
    if rc != 0:
        logger.error("tailscale cert failed (exit %d): %s", rc, err)
        for tmp in (tmp_cert, tmp_key):
            tmp.unlink(missing_ok=True)
        return False

    os.replace(tmp_cert, cert_path)
    os.replace(tmp_key, key_path)
    os.chmod(cert_path, 0o644)
    os.chmod(key_path, 0o600)
    logger.info("Renewed TLS cert for %s", domain)
    return True


async def _reload_caddy() -> None:
    docker = _resolve_bin("docker")
    if docker is None:
        logger.error(
            "New TLS cert is in place but `docker` was not found, so Caddy still "
            "holds the old cert. Run: docker compose restart caddy"
        )
        return

    rc, err = await _run(
        docker, "exec", "nexus-caddy-1",
        "caddy", "reload", "--config", "/etc/caddy/Caddyfile",
    )
    if rc == 0:
        logger.info("Caddy reloaded with new TLS certs")
    else:
        logger.error("Caddy reload failed (exit %d): %s", rc, err)


async def tls_renewal_loop(domain: str, cert_dir: str) -> None:
    cert_path = Path(cert_dir) / f"{domain}.crt"
    key_path = Path(cert_dir) / f"{domain}.key"
    while True:
        try:
            # Check before sleeping: on startup an already-expired cert must be
            # noticed now, not CHECK_INTERVAL from now.
            if not cert_path.exists():
                logger.warning("TLS cert not found at %s", cert_path)
            else:
                days_left = _days_until_expiry(cert_path)
                if days_left is None:
                    pass  # unparseable; _days_until_expiry already logged it
                elif days_left > RENEW_WITHIN_DAYS:
                    logger.debug("TLS cert has %.1f days left", days_left)
                else:
                    if days_left <= 0:
                        logger.warning("TLS cert EXPIRED %.1f days ago, renewing", -days_left)
                    else:
                        logger.info("TLS cert expires in %.1f days, renewing", days_left)
                    if await _renew_cert(domain, cert_path, key_path):
                        await _reload_caddy()

            await asyncio.sleep(CHECK_INTERVAL)

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("TLS renewal error: %s", e)
            await asyncio.sleep(CHECK_INTERVAL)
