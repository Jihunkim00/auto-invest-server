from __future__ import annotations

from types import SimpleNamespace

from app.brokers.kis_client import KisClient


def _client(response):
    client = KisClient.__new__(KisClient)
    client.settings = SimpleNamespace(kis_env="prod")
    client._request_balance = lambda: response
    return client


def test_balance_preserves_cash_withdrawable_d1_d2_and_unknown_orderable():
    result = _client(
        {
            "output2": [
                {
                    "dnca_tot_amt": "960737",
                    "wdrw_psbl_tot_amt": "960737",
                    "nxdy_excc_amt": "960737",
                    "d2_cash": "1001456",
                    "tot_evlu_amt": "1001456",
                    "scts_evlu_amt": "0",
                }
            ]
        }
    ).get_account_balance()

    assert result["cash"] == 960737
    assert result["withdrawable_cash"] == 960737
    assert result["orderable_cash"] is None
    assert result["orderable_cash_status"] == "candidate_required"
    assert result["d1_cash"] == 960737
    assert result["d2_cash"] == 1001456
    assert result["total_asset_value"] == 1001456


def test_balance_keeps_explicit_orderable_field_independent():
    result = _client(
        {
            "output2": [
                {
                    "dnca_tot_amt": "960737",
                    "wdrw_psbl_tot_amt": "960737",
                    "ord_psbl_cash": "996274",
                    "nxdy_excc_amt": "960737",
                    "d2_cash": "1001456",
                    "tot_evlu_amt": "1001456",
                }
            ]
        }
    ).get_account_balance()

    assert result["cash"] == 960737
    assert result["withdrawable_cash"] == 960737
    assert result["orderable_cash"] == 996274
    assert result["orderable_cash_status"] == "ok"
    assert result["d1_cash"] == 960737
    assert result["d2_cash"] == 1001456