from app.brokers.base import BrokerConfigurationError, BrokerNotEnabledError
from app.config import get_settings


class KisClient:
    """Safe KIS Open API client skeleton.

    The official KIS samples use app key, app secret, account/product code,
    HTS ID, REST token, and websocket approval key concepts. This class stores
    those values and prepares future integration points, but it does not make
    network calls or submit orders.
    """

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        return all(
            [
                self.settings.kis_app_key,
                self.settings.kis_app_secret,
                self.settings.kis_account_no,
                self.settings.kis_account_product_code,
                self.settings.kis_base_url,
            ]
        )

    def build_headers(self, tr_id: str | None = None) -> dict[str, str]:
        self._require_configured()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "charset": "UTF-8",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
            "custtype": "P",
        }
        if self.settings.kis_access_token:
            headers["authorization"] = f"Bearer {self.settings.kis_access_token}"
        if tr_id:
            headers["tr_id"] = tr_id
        return headers

    def issue_access_token(self):
        self._require_configured()
        raise NotImplementedError(
            "KIS access token issuance is not implemented in this safe skeleton."
        )

    def issue_approval_key(self):
        self._require_configured()
        raise NotImplementedError(
            "KIS websocket approval key issuance is not implemented in this safe skeleton."
        )

    def get_domestic_stock_price(self, symbol: str):
        self._require_configured()
        raise NotImplementedError(
            f"KIS domestic stock price lookup is not implemented for {symbol}."
        )

    def get_account_balance(self):
        self._require_configured()
        raise NotImplementedError(
            "KIS account balance lookup is not implemented in this safe skeleton."
        )

    def list_open_orders(self):
        self._require_configured()
        raise NotImplementedError(
            "KIS open order lookup is not implemented in this safe skeleton."
        )

    def submit_order(self, *args, **kwargs):
        raise BrokerNotEnabledError(
            "KIS order submission is disabled. This connector is a non-trading skeleton."
        )

    def _require_configured(self) -> None:
        missing = []
        for field_name, env_name in [
            ("kis_app_key", "KIS_APP_KEY"),
            ("kis_app_secret", "KIS_APP_SECRET"),
            ("kis_account_no", "KIS_ACCOUNT_NO"),
            ("kis_account_product_code", "KIS_ACCOUNT_PRODUCT_CODE"),
            ("kis_base_url", "KIS_BASE_URL"),
        ]:
            if not getattr(self.settings, field_name, None):
                missing.append(env_name)

        if missing:
            raise BrokerConfigurationError(
                "KIS configuration is incomplete; missing "
                + ", ".join(missing)
                + "."
            )
