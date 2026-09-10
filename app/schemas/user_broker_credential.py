from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, SecretStr


Environment = Literal["paper", "live"]


class KisBrokerCredentialRequest(BaseModel):
    environment: Environment
    app_key: SecretStr = Field(min_length=1, max_length=300)
    app_secret: SecretStr = Field(min_length=1, max_length=300)
    hts_id: SecretStr = Field(min_length=1, max_length=100)
    account_no: SecretStr = Field(min_length=1, max_length=100)
    account_product_code: SecretStr = Field(min_length=1, max_length=20)

    def credentials(self) -> dict[str, str]:
        return {
            "environment": self.environment,
            "app_key": self.app_key.get_secret_value().strip(),
            "app_secret": self.app_secret.get_secret_value().strip(),
            "hts_id": self.hts_id.get_secret_value().strip(),
            "account_no": self.account_no.get_secret_value().strip(),
            "account_product_code": self.account_product_code.get_secret_value().strip(),
        }


class AlpacaBrokerCredentialRequest(BaseModel):
    environment: Environment
    api_key: SecretStr = Field(min_length=1, max_length=300)
    secret_key: SecretStr = Field(min_length=1, max_length=300)

    def credentials(self) -> dict[str, str]:
        return {
            "environment": self.environment,
            "api_key": self.api_key.get_secret_value().strip(),
            "secret_key": self.secret_key.get_secret_value().strip(),
        }

