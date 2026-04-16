"""Background task: check Tailscale TLS cert age, renew if >60 days old."""

import asyncio
import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

CHECK_INTERVAL = 6 * 3600  # 6 hours
MAX_AGE_DAYS = 60


async def tls_renewal_loop(domain: str, cert_dir: str) -> None:
    cert_path = Path(cert_dir) / f"{domain}.crt"
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL)
            if not cert_path.exists():
                logger.warning("TLS cert not found at %s", cert_path)
                continue

            age_days = (asyncio.get_event_loop().time() - cert_path.stat().st_mtime) / 86400
            if age_days < MAX_AGE_DAYS:
                logger.debug("TLS cert age: %.1f days (threshold: %d)", age_days, MAX_AGE_DAYS)
                continue

            logger.info("TLS cert is %.0f days old, renewing via tailscale cert", age_days)

            proc = await asyncio.create_subprocess_exec(
                "tailscale", "cert", domain,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.error("tailscale cert failed: %s", stderr.decode())
                continue

            for ext in (".crt", ".key"):
                src = f"{domain}{ext}"
                if os.path.exists(src):
                    shutil.copy2(src, cert_dir)
                    logger.info("Copied %s to %s", src, cert_dir)

            reload_proc = await asyncio.create_subprocess_exec(
                "docker", "exec", "nexus-caddy-1", "caddy", "reload",
                "--config", "/etc/caddy/Caddyfile",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, reload_err = await reload_proc.communicate()
            if reload_proc.returncode == 0:
                logger.info("Caddy reloaded with new TLS certs")
            else:
                logger.error("Caddy reload failed: %s", reload_err.decode())

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning("TLS renewal error: %s", e)
