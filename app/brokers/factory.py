from app.brokers.alpaca_broker import AlpacaBroker
from app.brokers.base import Broker, BrokerConfigurationError, BrokerNotEnabledError
from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.config import get_settings


def get_broker(settings=None) -> Broker:
    settings = settings or get_settings()
    provider = _normalize_provider(settings.broker_provider)

    if provider == "alpaca":
        return AlpacaBroker()

    if provider == "kis":
        if not settings.kis_enabled:
            raise BrokerNotEnabledError(
                "BROKER_PROVIDER=kis was requested, but KIS_ENABLED=false."
            )
        return KisBroker(KisClient(settings))

    raise BrokerConfigurationError(f"Unknown BROKER_PROVIDER: {settings.broker_provider}")


def get_broker_status(settings=None, db=None) -> dict:
    settings = settings or get_settings()
    active_provider = _normalize_provider(settings.broker_provider)
    kis_auth = KisAuthManager(settings, db)
    kis_auth_status = kis_auth.get_auth_status()

    return {
        "active_provider": active_provider,
        "alpaca_available": bool(settings.alpaca_api_key and settings.alpaca_secret_key),
        "kis_enabled": bool(settings.kis_enabled),
        "kis_configured": kis_auth_status["kis_configured"],
        "kis_env": settings.kis_env,
        "kis_account_no_masked": mask_account_no(settings.kis_account_no),
        "kis_has_access_token": kis_auth_status["has_access_token"],
        "kis_has_approval_key": kis_auth_status["has_approval_key"],
    }


def mask_account_no(account_no: str | None) -> str | None:
    if not account_no:
        return None

    value = str(account_no).strip()
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


def _normalize_provider(provider: str | None) -> str:
    return (provider or "alpaca").strip().lower()
