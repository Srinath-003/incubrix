import os
from unittest.mock import patch
from app.config import Settings


def test_default_config_loading():
    """Settings load cleanly with sensible development defaults."""
    settings = Settings()
    assert settings.app_name == "IncuBrix Distribution Engine"
    assert settings.app_port == 8000
    assert settings.mongodb_db_name == "incubrix"
    assert settings.mongodb_timeout_ms == 2000


def test_env_override_config():
    """Environment variables successfully override default settings."""
    with patch.dict(
        os.environ,
        {
            "APP_PORT": "9090",
            "APP_ENV": "production",
            "MONGODB_DB_NAME": "incubrix_prod",
            "MONGODB_TIMEOUT_MS": "5000",
        },
    ):
        settings = Settings()
        assert settings.app_port == 9090
        assert settings.app_env == "production"
        assert settings.mongodb_db_name == "incubrix_prod"
        assert settings.mongodb_timeout_ms == 5000


def test_no_hardcoded_secrets_in_gitignore():
    """Verify .env files and credentials are appropriately protected in .gitignore."""
    gitignore_path = os.path.join(os.path.dirname(__file__), "..", ".gitignore")
    assert os.path.exists(gitignore_path)
    with open(gitignore_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".env" in content
    assert "*.key" in content
    assert "*.pem" in content
