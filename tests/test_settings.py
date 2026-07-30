import pytest

from src.core.settings import Settings


class TestSettingsValidation:
    def test_dev_allows_default_password(self) -> None:
        s = Settings(ENVIRONMENT="development", POSTGRES_PASSWORD="CHANGE_ME")
        assert s.postgres_password == "CHANGE_ME"
        assert s.environment == "development"

    def test_prod_rejects_default_password(self) -> None:
        with pytest.raises(ValueError, match="CHANGE_ME"):
            Settings(ENVIRONMENT="production", POSTGRES_PASSWORD="CHANGE_ME")

    def test_prod_allows_custom_password(self) -> None:
        s = Settings(ENVIRONMENT="production", POSTGRES_PASSWORD="s3cret!")
        assert s.postgres_password == "s3cret!"
        assert s.environment == "production"

    def test_default_environment_is_dev(self) -> None:
        s = Settings()
        assert s.environment == "development"
