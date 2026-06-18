from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openai import OpenAI
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AgentCommandLog
from app.schemas.agent_command import (
    SCHEMA_VERSION,
    AgentCommandParseResponse,
    AutoInvestCommand,
    CommandDomain,
    CommandType,
    OrderSide,
)
from app.services.agent_command_validator import AgentCommandValidator


logger = logging.getLogger(__name__)


AGENT_COMMAND_SYSTEM_PROMPT = """
You are an Auto Invest command parser.
Convert Korean or English natural language into a strict AutoInvestCommand JSON object.
You must not execute trades.
You must not claim an order was placed.
You must not bypass authentication.
Default to hold/analyze-only when uncertain.
If symbol, market, amount, side, or timing is ambiguous, set needs_clarification=true.
Live orders always require auth and risk approval.
Settings that reduce safety require auth.
Return only JSON matching AutoInvestCommand v1 schema.
"""


class AgentCommandParserService:
    def __init__(
        self,
        *,
        openai_client: Any | None = None,
        validator: AgentCommandValidator | None = None,
        settings: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.openai_model = getattr(
            self.settings,
            "agent_chat_model",
            getattr(self.settings, "openai_model", "gpt-5.4-mini"),
        )
        self.openai_reasoning_effort = getattr(
            self.settings,
            "agent_chat_reasoning_effort",
            getattr(self.settings, "openai_reasoning_effort", "low"),
        )
        self.openai_temperature = getattr(self.settings, "agent_chat_temperature", 0.0)
        self.openai_timeout_seconds = getattr(
            self.settings,
            "agent_chat_timeout_seconds",
            20.0,
        )
        self.fallback_enabled = getattr(self.settings, "agent_chat_fallback_enabled", True)
        self.validator = validator or AgentCommandValidator()
        if openai_client is not None:
            self.client = openai_client
        else:
            api_key = getattr(self.settings, "openai_api_key", None)
            self.client = (
                OpenAI(api_key=api_key, timeout=self.openai_timeout_seconds)
                if api_key
                else None
            )

    def parse(
        self,
        db: Session,
        *,
        message: str,
        conversation_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        clean_message = str(message or "").strip()
        if not clean_message:
            clean_message = ""

        parser_status = "fallback"
        model_name: str | None = None
        error_message: str | None = None

        try:
            payload, parser_status, model_name = self._parse_with_gpt_if_available(
                clean_message,
                context,
            )
        except Exception as exc:
            logger.info("Agent command GPT parse failed; using fallback: %s", exc)
            payload = self._fallback_parse(clean_message, context)
            parser_status = "failed_fallback_used"
            model_name = self.openai_model if self.client else None
            error_message = self._safe_exc_message(exc)

        command = self.validator.validate_and_normalize(
            payload,
            context=context,
            fallback_message=clean_message,
        )
        row = self._store_command_log(
            db,
            conversation_id=conversation_id,
            user_message=clean_message,
            parser_status=parser_status,
            command=command,
            model_name=model_name,
            error_message=error_message,
        )
        response = AgentCommandParseResponse(
            status="parsed",
            parser_status=parser_status,
            command=command,
            safety=command.safety,
            command_log_id=row.id,
            model_name=model_name,
            error_message=error_message,
        )
        return response.model_dump(mode="json")

    def _parse_with_gpt_if_available(
        self,
        message: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], str, str | None]:
        if not self.client:
            return self._fallback_parse(message, context), "fallback", None

        payload = self._call_openai(message, context)
        if not self.validator.is_candidate_payload(payload):
            raise ValueError("OpenAI response did not match AutoInvestCommand v1 envelope")
        return payload, "gpt", self.openai_model

    def _call_openai(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        prompt_payload = {
            "message": message,
            "context": context,
            "schema_version": SCHEMA_VERSION,
            "required_safety": {
                "execution_blocked_in_pr56": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "setting_changed": False,
                "scheduler_changed": False,
            },
        }
        response = self.client.responses.create(
            model=self.openai_model,
            reasoning={"effort": self.openai_reasoning_effort},
            temperature=self.openai_temperature,
            instructions=AGENT_COMMAND_SYSTEM_PROMPT,
            input=json.dumps(prompt_payload, ensure_ascii=False),
        )
        raw_text = (response.output_text or "").strip()
        if not raw_text:
            raise ValueError("OpenAI returned empty output_text")
        return self._parse_json_text(raw_text)

    def _parse_json_text(self, raw_text: str) -> dict[str, Any]:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("Could not locate JSON object in OpenAI response")
            text = text[start : end + 1]
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("OpenAI response JSON was not an object")
        return payload

    def _fallback_parse(self, message: str, context: dict[str, Any]) -> dict[str, Any]:
        text = (message or "").strip()
        lowered = text.lower()
        symbol = self._detect_symbol(text)
        market = self._resolve_market(context, symbol)
        provider = self._resolve_provider(context, market)

        if self._is_recent_orders_request(text):
            return self._base_payload(
                CommandType.SHOW_RECENT_ORDERS,
                CommandDomain.LOGS,
                "show_recent_orders",
                market,
                provider,
                summary="최근 주문 기록을 조회하는 명령으로 해석했습니다. 실제 주문은 실행하지 않았습니다.",
                confidence=0.86,
            )

        if self._is_positions_request(text):
            return self._base_payload(
                CommandType.SHOW_POSITIONS,
                CommandDomain.POSITION,
                "show_positions",
                market,
                provider,
                summary="보유 종목과 포지션을 조회하는 명령으로 해석했습니다. 실제 주문은 실행하지 않았습니다.",
                confidence=0.88,
            )

        if "kill switch" in lowered or "킬 스위치" in text or "킬스위치" in text:
            value = self._detect_enable_value(text)
            if value is not None:
                return self._settings_payload(
                    CommandType.SET_KILL_SWITCH,
                    CommandDomain.SAFETY,
                    "set_kill_switch",
                    "kill_switch",
                    value,
                    market,
                    provider,
                    "kill switch를 켜는 명령입니다. PR56에서는 실제 설정을 변경하지 않습니다."
                    if value
                    else "kill switch를 끄는 위험 설정 명령입니다. 본인 인증이 필요하며 PR56에서는 실제 설정을 변경하지 않습니다.",
                    confidence=0.9,
                )

        if "dry run" in lowered or "드라이런" in text or "드라이 런" in text:
            value = self._detect_enable_value(text)
            if value is not None:
                return self._settings_payload(
                    CommandType.SET_DRY_RUN,
                    CommandDomain.SETTINGS,
                    "set_dry_run",
                    "dry_run",
                    value,
                    market,
                    provider,
                    "dry_run을 켜는 명령입니다. PR56에서는 실제 설정을 변경하지 않습니다."
                    if value
                    else "dry_run을 끄는 위험 설정 명령입니다. 본인 인증이 필요하며 PR56에서는 실제 설정을 변경하지 않습니다.",
                    confidence=0.9,
                )

        if self._is_limited_auto_sell_enable(text):
            return self._settings_payload(
                CommandType.REQUEST_LIMITED_AUTO_SELL_ENABLE,
                CommandDomain.LIMITED_AUTO,
                "request_limited_auto_sell_enable",
                "kis_limited_auto_sell_enabled",
                True,
                market,
                provider,
                "limited auto sell 활성화 요청입니다. 본인 인증과 리스크 승인이 필요하며 PR56에서는 실제 설정을 변경하지 않습니다.",
                confidence=0.86,
                high_risk=True,
            )

        if self._is_auto_buy_enable(text):
            return self._settings_payload(
                CommandType.SET_KIS_LIVE_AUTO_BUY,
                CommandDomain.SETTINGS,
                "request_kis_live_auto_buy_enable",
                "kis_live_auto_buy_enabled",
                True,
                market,
                provider,
                "auto-buy 활성화 요청입니다. 고위험 명령이므로 본인 인증과 리스크 승인이 필요하며 PR56 이후 승인/실행 단계 전까지 비활성 상태로 유지됩니다.",
                confidence=0.86,
                high_risk=True,
            )

        if self._is_disable_new_entries(text):
            payload = self._settings_payload(
                CommandType.REQUEST_SETTING_CHANGE,
                CommandDomain.RISK,
                "disable_new_entries_temporarily",
                "new_entries_enabled",
                False,
                market,
                provider,
                "이번 주 신규 매수를 막는 리스크 설정 요청입니다. PR56에서는 실제 설정을 변경하지 않습니다.",
                confidence=0.82,
            )
            payload["risk_change"] = {
                "key": "new_entries_enabled",
                "value": False,
                "direction": "increase_safety",
                "high_risk": False,
            }
            return payload

        if self._is_manual_sell_prefill(text) and symbol:
            return self._base_payload(
                CommandType.PREPARE_MANUAL_SELL_TICKET,
                CommandDomain.ORDER,
                "prepare_manual_sell_ticket",
                market,
                provider,
                symbol=symbol,
                side=OrderSide.SELL.value,
                summary=f"{self._display_symbol(symbol)} 매도 티켓을 준비하는 명령으로 해석했습니다. PR56에서는 티켓 생성이나 주문 실행을 하지 않습니다.",
                confidence=0.83,
            )

        if self._is_conditional_buy_schedule(text) and symbol:
            amount = self._parse_krw_amount(text)
            schedule = self._parse_schedule(text, context)
            return self._base_payload(
                CommandType.CREATE_AGENT_PLAN,
                CommandDomain.AGENT,
                "conditional_buy_schedule",
                market,
                provider,
                symbol=symbol,
                side=OrderSide.BUY.value,
                budget={
                    "amount": amount,
                    "currency": "KRW" if market == "KR" else "USD",
                    "mode": "max_notional",
                }
                if amount is not None
                else None,
                schedule=schedule,
                summary=(
                    f"{self._display_symbol(symbol)}를 조건 충족 시 최대 {int(amount):,}원까지 매수 가능한 계획으로 해석했습니다. "
                    "실주문 전 본인 인증과 리스크 승인이 필요하며 PR56에서는 실행하지 않습니다."
                )
                if amount is not None
                else (
                    f"{self._display_symbol(symbol)} 조건부 매수 계획으로 해석했지만 금액 확인이 필요합니다. "
                    "PR56에서는 실행하지 않습니다."
                ),
                confidence=0.9 if amount is not None and schedule else 0.72,
            )

        if self._is_single_symbol_analysis(text) and symbol:
            return self._base_payload(
                CommandType.RUN_SINGLE_SYMBOL_ANALYSIS,
                CommandDomain.ANALYSIS,
                "single_symbol_analysis",
                market,
                provider,
                symbol=symbol,
                summary=f"{self._display_symbol(symbol)} 분석 요청으로 해석했습니다. PR56에서는 분석 실행 없이 명령 JSON만 반환합니다.",
                confidence=0.86,
            )

        if self._is_ambiguous_buy_request(text) and symbol:
            return self._base_payload(
                CommandType.CLARIFY_REQUEST,
                CommandDomain.ORDER,
                "ambiguous_buy_request",
                market,
                provider,
                symbol=symbol,
                side=OrderSide.BUY.value,
                needs_clarification=True,
                clarification_question="매수 금액 또는 수량, 조건, 실행 시점을 알려주세요.",
                summary=f"{self._display_symbol(symbol)} 매수 요청으로 보이지만 금액, 조건, 시점이 부족합니다. 실제 주문은 실행하지 않았습니다.",
                confidence=0.58,
            )

        return self.validator.safe_unknown_payload(text, context=context)

    def _base_payload(
        self,
        command_type: CommandType,
        domain: CommandDomain,
        intent: str,
        market: str,
        provider: str,
        *,
        symbol: str | None = None,
        side: str = OrderSide.NONE.value,
        quantity: float | None = None,
        budget: dict[str, Any] | None = None,
        schedule: dict[str, Any] | None = None,
        settings_change: dict[str, Any] | None = None,
        risk_change: dict[str, Any] | None = None,
        portfolio_scope: dict[str, Any] | None = None,
        needs_clarification: bool = False,
        clarification_question: str | None = None,
        summary: str = "Command parsed for review. No action was executed.",
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "command_type": command_type.value,
            "domain": domain.value,
            "intent": intent,
            "market": market,
            "provider": provider,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "budget": budget,
            "schedule": schedule,
            "settings_change": settings_change,
            "risk_change": risk_change,
            "portfolio_scope": portfolio_scope,
            "needs_clarification": needs_clarification,
            "clarification_question": clarification_question,
            "user_visible_summary": summary,
            "parser_confidence": confidence,
        }

    def _settings_payload(
        self,
        command_type: CommandType,
        domain: CommandDomain,
        intent: str,
        key: str,
        value: Any,
        market: str,
        provider: str,
        summary: str,
        *,
        confidence: float,
        high_risk: bool = False,
    ) -> dict[str, Any]:
        payload = self._base_payload(
            command_type,
            domain,
            intent,
            market,
            provider,
            settings_change={
                "key": key,
                "value": value,
                "safety_direction": "increase_safety" if value is True and key == "kill_switch" else None,
            },
            summary=summary,
            confidence=confidence,
        )
        if high_risk:
            payload["risk_change"] = {
                "key": key,
                "value": value,
                "direction": "increase_risk",
                "high_risk": True,
            }
        return payload

    def _store_command_log(
        self,
        db: Session,
        *,
        conversation_id: str | None,
        user_message: str,
        parser_status: str,
        command: AutoInvestCommand,
        model_name: str | None,
        error_message: str | None,
    ) -> AgentCommandLog:
        command_json = command.model_dump(mode="json")
        safety_json = command.safety.model_dump(mode="json")
        row = AgentCommandLog(
            conversation_id=conversation_id,
            user_message=user_message,
            parser_status=parser_status,
            command_type=command.command_type.value,
            domain=command.domain.value,
            market=command.market.value,
            provider=command.provider.value,
            symbol=command.symbol,
            side=command.side.value,
            risk_level=command.risk_level.value,
            requires_auth=command.requires_auth,
            needs_clarification=command.needs_clarification,
            parsed_command_json=json.dumps(command_json, ensure_ascii=False),
            safety_json=json.dumps(safety_json, ensure_ascii=False),
            model_name=model_name,
            schema_version=command.schema_version,
            error_message=error_message,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _detect_symbol(self, text: str) -> str | None:
        compact = re.sub(r"\s+", "", text)
        symbol_aliases = {
            "삼성전자": "005930",
            "삼전": "005930",
            "네이버": "035420",
            "NAVER": "035420",
            "카카오": "035720",
            "SK하이닉스": "000660",
            "하이닉스": "000660",
        }
        upper_text = text.upper()
        for alias, symbol in symbol_aliases.items():
            if alias.upper() in upper_text or alias in compact:
                return symbol
        six_digit = re.search(r"\b\d{6}\b", text)
        if six_digit:
            return six_digit.group(0)
        us_symbol = re.search(r"\b[A-Z]{1,5}\b", upper_text)
        if us_symbol:
            candidate = us_symbol.group(0)
            if candidate not in {"KR", "US", "KIS", "GPT"}:
                return candidate
        return None

    def _resolve_market(self, context: dict[str, Any], symbol: str | None) -> str:
        raw = str(context.get("default_market") or context.get("market") or "").strip().upper()
        if raw in {"US", "KR", "ALL"}:
            return raw
        if symbol and re.fullmatch(r"\d{6}", symbol):
            return "KR"
        if symbol:
            return "US"
        return "UNKNOWN"

    def _resolve_provider(self, context: dict[str, Any], market: str) -> str:
        raw = str(context.get("default_provider") or context.get("provider") or "").strip().lower()
        if raw in {"alpaca", "kis", "all"}:
            return raw
        if market == "KR":
            return "kis"
        if market == "US":
            return "alpaca"
        return "unknown"

    def _detect_enable_value(self, text: str) -> bool | None:
        lowered = text.lower()
        if any(token in lowered for token in [" off", "disable", "false"]) or any(
            token in text for token in ["꺼", "끄", "중지", "비활성"]
        ):
            return False
        if any(token in lowered for token in [" on", "enable", "true"]) or any(
            token in text for token in ["켜", "활성"]
        ):
            return True
        return None

    def _parse_krw_amount(self, text: str) -> float | None:
        compact = text.replace(",", "")
        man = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원?", compact)
        if man:
            return float(man.group(1)) * 10000
        won = re.search(r"(\d+(?:\.\d+)?)\s*원", compact)
        if won:
            return float(won.group(1))
        plain = re.search(r"(\d{4,})", compact)
        if plain:
            return float(plain.group(1))
        return None

    def _parse_schedule(self, text: str, context: dict[str, Any]) -> dict[str, Any] | None:
        if "내일" not in text and not re.search(r"\d{1,2}\s*시", text):
            return None
        timezone_name = str(context.get("timezone") or "Asia/Seoul")
        tz = self._timezone(timezone_name)
        now = datetime.now(tz)
        target_date = now.date() + timedelta(days=1) if "내일" in text else now.date()
        hour_match = re.search(r"(\d{1,2})\s*시", text)
        hour = int(hour_match.group(1)) if hour_match else 9
        run_at = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            max(0, min(hour, 23)),
            0,
            0,
            tzinfo=tz,
        )
        return {
            "type": "once",
            "run_at": run_at.isoformat(),
            "timezone": timezone_name,
            "raw_time_text": "내일" if "내일" in text else text,
        }

    def _timezone(self, timezone_name: str):
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            if timezone_name in {"Asia/Seoul", "KST"}:
                return timezone(timedelta(hours=9))
            return timezone.utc

    def _is_recent_orders_request(self, text: str) -> bool:
        return "주문" in text and any(token in text for token in ["기록", "내역", "보여", "조회"])

    def _is_positions_request(self, text: str) -> bool:
        lowered = text.lower()
        return any(token in text for token in ["보유종목", "보유 종목", "포지션"]) or "positions" in lowered

    def _is_limited_auto_sell_enable(self, text: str) -> bool:
        lowered = text.lower()
        return (
            ("limited auto sell" in lowered or ("limited" in lowered and "sell" in lowered))
            and self._detect_enable_value(text) is True
        )

    def _is_auto_buy_enable(self, text: str) -> bool:
        lowered = text.lower()
        return (
            ("auto buy" in lowered or "자동 매수" in text)
            and self._detect_enable_value(text) is True
        )

    def _is_disable_new_entries(self, text: str) -> bool:
        return "신규 매수" in text and any(token in text for token in ["하지 마", "하지마", "중지", "막아", "금지"])

    def _is_manual_sell_prefill(self, text: str) -> bool:
        return any(token in text for token in ["매도", "팔"]) and any(token in text for token in ["준비", "티켓"])

    def _is_conditional_buy_schedule(self, text: str) -> bool:
        has_buy = any(token in text for token in ["사줘", "매수"])
        has_condition = any(token in text for token in ["조건", "맞으면", "충족"])
        has_timing = "내일" in text or re.search(r"\d{1,2}\s*시", text)
        return has_buy and has_condition and bool(has_timing)

    def _is_single_symbol_analysis(self, text: str) -> bool:
        return any(token in text for token in ["살만한지", "분석", "봐줘", "검토"]) and "사줘" not in text

    def _is_ambiguous_buy_request(self, text: str) -> bool:
        return any(token in text for token in ["사줘", "매수"]) and "살만한지" not in text

    def _display_symbol(self, symbol: str) -> str:
        if symbol == "005930":
            return "삼성전자(005930)"
        return symbol

    def _safe_exc_message(self, exc: Exception) -> str:
        text = str(exc).strip()
        if not text:
            return exc.__class__.__name__
        if len(text) > 240:
            return f"{exc.__class__.__name__}: {text[:240]}..."
        return f"{exc.__class__.__name__}: {text}"
