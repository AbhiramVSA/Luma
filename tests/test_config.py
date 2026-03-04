"""Tests for configuration and settings."""

from config.config import Settings


class TestSettingsAllowedOrigins:
    def test_default_origins_when_empty(self):
        s = Settings(
            OPENAI_API_KEY="test",
            DATABASE_URL="postgresql+asyncpg://x",
            JWT_SECRET_KEY="secret",
        )
        origins = s.allowed_origins
        assert "http://localhost:3000" in origins

    def test_frontend_origin_included(self):
        s = Settings(
            OPENAI_API_KEY="test",
            DATABASE_URL="postgresql+asyncpg://x",
            JWT_SECRET_KEY="secret",
            FRONTEND_URL="https://app.example.com/",
        )
        origins = s.allowed_origins
        assert "https://app.example.com" in origins

    def test_additional_origins_parsed(self):
        s = Settings(
            OPENAI_API_KEY="test",
            DATABASE_URL="postgresql+asyncpg://x",
            JWT_SECRET_KEY="secret",
            FRONTEND_URL="https://app.example.com",
            CORS_ADDITIONAL_ORIGINS="https://a.com, https://b.com",
        )
        origins = s.allowed_origins
        assert "https://a.com" in origins
        assert "https://b.com" in origins

    def test_trailing_slashes_stripped(self):
        s = Settings(
            OPENAI_API_KEY="test",
            DATABASE_URL="postgresql+asyncpg://x",
            JWT_SECRET_KEY="secret",
            FRONTEND_URL="https://app.example.com/",
        )
        for origin in s.allowed_origins:
            assert not origin.endswith("/")
