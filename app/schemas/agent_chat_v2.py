from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentChatV2MessageRequest(BaseModel):
    """Stable V2 request envelope kept separate from the legacy send contract."""

    conversation_key: str | None = Field(default=None, max_length=80)
    message: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    auto_create_conversation: bool = True
    language: str = Field(default="ko", max_length=10)
    locale: str = Field(default="ko-KR", max_length=20)

    def legacy_payload(self) -> dict[str, Any]:
        return {
            "conversation_key": self.conversation_key,
            "message": self.message,
            "context": self.context,
            "auto_create_conversation": self.auto_create_conversation,
            "language": self.language,
            "locale": self.locale,
        }
