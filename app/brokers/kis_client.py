from app.brokers.base import BrokerNotEnabledError
from app.brokers.kis_auth_manager import KisAuthManager
from app.config import get_settings


class KisClient:
    """Safe KIS Open API client skeleton.

    The official KIS samples use app key, app secret, account/product code,
    HTS ID, REST token, and websocket approval key concepts. This class stores
    those values and prepares future integration points, but it does not submit
    orders.
    """

    def __init__(self, settings=None, auth_manager: KisAuthManager | None = None):
        self.settings = settings or get_settings()
        self.auth_manager = auth_manager or KisAuthManager(self.settings)

    def is_configured(self) -> bool:
        return self.auth_manager.is_configured()

    def get_access_token(self, force_refresh: bool = False):
        return self.auth_manager.get_valid_access_token(force_refresh=force_refresh)

    def get_approval_key(self, force_refresh: bool = False):
        return self.auth_manager.get_valid_approval_key(force_refresh=force_refresh)

    def build_headers(
        self,
        tr_id: str | None = None,
        *,
        include_auth: bool = True,
    ) -> dict[str, str]:
        self.auth_manager.require_configured()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "charset": "UTF-8",
            "appkey": self.settings.kis_app_key,
            "appsecret": self.settings.kis_app_secret,
            "custtype": "P",
        }
        if include_auth:
            token = self.get_access_token()
            headers["authorization"] = f"Bearer {token.token}"
        if tr_id:
            headers["tr_id"] = tr_id
        return headers

    def issue_access_token(self):
        return self.get_access_token(force_refresh=True)

    def issue_approval_key(self):
        return self.get_approval_key(force_refresh=True)

    def get_domestic_stock_price(self, symbol: str):
        self.auth_manager.require_configured()
        raise NotImplementedError(
            f"KIS domestic stock price lookup is not implemented for {symbol}."
        )

    def get_account_balance(self):
        self.auth_manager.require_configured()
        raise NotImplementedError(
            "KIS account balance lookup is not implemented in this safe skeleton."
        )

    def list_open_orders(self):
        self.auth_manager.require_configured()
        raise NotImplementedError(
            "KIS open order lookup is not implemented in this safe skeleton."
        )

    def submit_order(self, *args, **kwargs):
        raise BrokerNotEnabledError(
            "KIS order submission is disabled. This connector is a non-trading skeleton."
        )
