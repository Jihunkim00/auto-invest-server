import json

import pytest
import requests

from app.services.account_snapshot_retry import account_snapshot_failure_diagnostics, retryable_kis_account_snapshot_error
from app.services.user_broker_account_service import (
    UserKisReadOnlyClient, UserKisTokenManager, UserBrokerUnavailableError, KIS_BALANCE_PATH,
)
from app.tests.test_user_broker_accounts import FakeResponse, FakeBrokerHttp


@pytest.mark.parametrize('operation', ['token', 'balance', 'open_orders'])
@pytest.mark.parametrize('kind', ['429', '500', '502', '503', 'Timeout', 'ConnectionError', 'json', 'shape', 'kis_code'])
def test_failure_operation_http_code_and_safe_retry_diagnostics(operation, kind):
    secret = 'DO_NOT_LOG_CREDENTIALS_OR_ACCOUNT'

    class BadJson(FakeResponse):
        def json(self):
            raise ValueError(secret)

    def fault():
        if kind.isdigit():
            return FakeResponse({'msg1': secret}, int(kind))
        if kind in {'Timeout', 'ConnectionError'}:
            raise getattr(requests.exceptions, kind)(secret)
        if kind == 'json':
            return BadJson({})
        if kind == 'shape':
            return FakeResponse([] if operation == 'token' else {'rt_cd': '0'})
        return FakeResponse({'rt_cd': '1', 'msg_cd': 'EGW00201', 'msg1': secret})

    class Http(FakeBrokerHttp):
        def post(self, *args, **kwargs):
            return fault() if operation == 'token' else super().post(*args, **kwargs)

        def get(self, url, **kwargs):
            target = 'balance' if url.endswith(KIS_BALANCE_PATH) else 'open_orders'
            return fault() if operation == target else super().get(url, **kwargs)

    client = UserKisReadOnlyClient(user_id=2, credentials={
        'environment': 'live', 'app_key': 'fake-key', 'app_secret': secret,
        'account_no': '12345678', 'account_product_code': '01'}, credential_identity='fake-2',
        http_client=Http(), token_manager=UserKisTokenManager())
    with pytest.raises(UserBrokerUnavailableError) as raised:
        client.get_snapshot()
    assert retryable_kis_account_snapshot_error(raised.value)
    details = account_snapshot_failure_diagnostics(raised.value, attempt=1, retryable=True)
    assert details['read_operation'] == operation
    assert details['owner_user_id'] == 2 and details['environment'] == 'live'
    assert details['duration_ms'] >= 0 and details['queried_at']
    assert details['attempts'] == 1 and details['max_attempts'] == 3
    if kind.isdigit():
        assert details['http_status'] == int(kind)
    if kind == 'kis_code':
        assert details['msg_cd'] == 'EGW00201'
    assert secret not in json.dumps(details)
    assert '12345678' not in json.dumps(details)
    assert 'msg1' not in details
