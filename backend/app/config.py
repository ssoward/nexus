import functools
import os
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _validate_no_secret_keys(obj: Any, path: str = "") -> None:
    """Prevent secrets from being placed in config.yml."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = k.lower()
            if any(s in key_lower for s in ["secret", "password", "token", "apikey", "api_key"]):
                raise ValueError(
                    f"Secret-looking key '{path}.{k}' found in config.yml — use env vars instead"
                )
            _validate_no_secret_keys(v, f"{path}.{k}")


def _load_yaml_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        data = yaml.safe_load(f)
    if data:
        _validate_no_secret_keys(data)
    return data or {}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Secrets — must come from environment, never from config.yml
    app_secret: str
    jwt_secret: str
    crypto_salt: str

    # JWT settings
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    ws_token_expire_seconds: int = 60

    # App settings (can be overridden by config.yml)
    db_path: str = "~/.nexus/nexus.db"
    log_level: str = "INFO"
    log_format: str = "text"  # "text" or "json"
    max_panes: int = 6
    session_idle_timeout_seconds: int = 3600

    # TLS auto-renewal
    tls_domain: str = ""
    tls_auto_renew: bool = False
    tls_cert_dir: str = "./certs"

    # Session recovery
    recovery_enabled: bool = False
    recovery_ttl_hours: int = 1
    default_cols: int = 220
    default_rows: int = 50

    # Command presets for session creation
    presets: list[dict] = [
        {"name": "bash", "command": ["/bin/bash", "-l"], "description": "Login shell"},
        {"name": "zsh",  "command": ["/bin/zsh",  "-l"], "description": "Zsh login shell"},
        {"name": "claude", "command": ["claude"],          "description": "Claude Code CLI"},
        {"name": "python", "command": ["python3"],         "description": "Python 3 REPL"},
    ]

    # SMTP for Email OTP (optional — only needed if email_otp MFA is used)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # TOTP config
    totp_issuer: str = "Nexus"

    @field_validator("app_secret")
    @classmethod
    def app_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("APP_SECRET must be at least 32 characters")
        return v

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    @field_validator("crypto_salt")
    @classmethod
    def crypto_salt_length(cls, v: str) -> str:
        if len(v) < 16:
            raise ValueError("CRYPTO_SALT must be at least 16 characters")
        return v

    @model_validator(mode="after")
    def expand_paths(self) -> "Settings":
        self.db_path = os.path.expanduser(self.db_path)
        return self

    def __repr__(self) -> str:
        return "Settings(<redacted>)"

    def __str__(self) -> str:
        return "Settings(<redacted>)"


@functools.lru_cache
def get_settings() -> Settings:
    yaml_config = _load_yaml_config(os.getenv("CONFIG_PATH", "/app/config.yml"))

    # Extract flat values from nested YAML
    env_overrides: dict[str, Any] = {}
    if yaml_config:
        app = yaml_config.get("app", {})
        session = yaml_config.get("session", {})
        resources = yaml_config.get("resources", {})
        if app.get("max_panes"):
            env_overrides["max_panes"] = app["max_panes"]
        if app.get("log_level"):
            env_overrides["log_level"] = app["log_level"]
        if app.get("db_path"):
            env_overrides["db_path"] = app["db_path"]
        if session.get("idle_timeout_seconds"):
            env_overrides["session_idle_timeout_seconds"] = session["idle_timeout_seconds"]
        if session.get("jwt_expire_minutes"):
            env_overrides["jwt_expire_minutes"] = session["jwt_expire_minutes"]
        if app.get("log_format"):
            env_overrides["log_format"] = app["log_format"]
        if yaml_config.get("presets"):
            env_overrides["presets"] = yaml_config["presets"]
        tls = yaml_config.get("tls", {})
        if tls.get("domain"):
            env_overrides["tls_domain"] = tls["domain"]
        if tls.get("auto_renew") is not None:
            env_overrides["tls_auto_renew"] = tls["auto_renew"]
        if tls.get("cert_dir"):
            env_overrides["tls_cert_dir"] = tls["cert_dir"]
        recovery = yaml_config.get("recovery", {})
        if recovery.get("enabled") is not None:
            env_overrides["recovery_enabled"] = recovery["enabled"]
        if recovery.get("ttl_hours"):
            env_overrides["recovery_ttl_hours"] = recovery["ttl_hours"]

    return Settings(**env_overrides)
