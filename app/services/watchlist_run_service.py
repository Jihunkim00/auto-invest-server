import uuid

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.constants import DEFAULT_GATE_LEVEL
from app.services.entry_readiness_service import evaluate_entry_readiness
from app.services.position_lifecycle_service import ENTRY_SCAN_MODE
from app.services.trading_orchestrator_service import TradingOrchestratorService
from app.services.watchlist_research_service import WatchlistResearchService
from app.services.watchlist_service import WatchlistService

_RISK_LEVEL_ORDER = {"low": 0, "normal": 1, "medium": 2, "high": 3}



def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default



def _risk_rank(value: object) -> int:
    risk = str(value).strip().lower()
    return _RISK_LEVEL_ORDER.get(risk, _RISK_LEVEL_ORDER["medium"])


class WatchlistRunService:
    def run_once(
        self,
        db: Session,
        *,
        trigger_source: str = "manual",
        gate_level: int = DEFAULT_GATE_LEVEL,
        source_endpoint: str = "/trading/run-watchlist-once",
        scheduler_slot: str | None = None,
    ):
        settings = get_settings()
        alpaca_base = str(settings.alpaca_base_url or "").lower()
        if "paper" not in alpaca_base:
            raise ValueError("Live Alpaca endpoint disabled for run-watchlist-once")

        watchlist = WatchlistService()
        research_service = WatchlistResearchService()
        analysis = watchlist.analyze(gate_level=gate_level)
        watchlist_rows = analysis.get("watchlist") or []
        top_candidate_count = settings.watchlist_top_candidates_for_research
        quant_weight = settings.watchlist_quant_weight
        research_weight = settings.watchlist_research_weight
        min_entry_score = settings.watchlist_min_entry_score
        min_quant_score = settings.watchlist_min_quant_score
        min_research_score = settings.watchlist_min_research_score
        strong_entry_score = settings.watchlist_strong_entry_score
        min_score_gap = settings.watchlist_min_score_gap
        max_sell_score = settings.watchlist_max_sell_score

        quant_candidates = sorted(
            watchlist_rows,
            key=lambda row: (
                0 if bool(row.get("entry_ready")) else 1,
                -_safe_float(row.get("quant_score", 0)),
                _safe_float(row.get("quant_sell_score", 100), 100.0),
            ),
        )[:top_candidate_count]
        top_quant_candidates = [
            {
                "symbol": candidate["symbol"],
                "quant_score": candidate["quant_score"],
                "quant_reason": candidate.get("quant_reason"),
                "entry_ready": bool(candidate.get("entry_ready")),
                "action_hint": candidate.get("action_hint", "watch"),
                "block_reason": candidate.get("block_reason"),
            }
            for candidate in quant_candidates
        ]

        researched_candidates: list[dict[str, object]] = []
        watchlist_order_map = {
            str(row.get("symbol", "")).upper(): index for index, row in enumerate(watchlist_rows)
        }
        for candidate in quant_candidates:
            symbol = candidate["symbol"].upper()
            scored_candidate, indicators = watchlist._score_symbol(symbol, gate_level=gate_level)
            research = research_service.analyze_candidate(
                db=db,
                symbol=symbol,
                indicators=indicators,
                gate_level=gate_level,
            )
            researched_candidate = {
                **scored_candidate,
                **research,
            }
            researched_candidate["final_entry_score"] = round(
                researched_candidate["quant_score"] * quant_weight
                + researched_candidate["market_research_score"] * research_weight,
                2,
            )
            sell_score = researched_candidate.get("sell_score")
            if sell_score is None:
                sell_score = researched_candidate.get("quant_sell_score", 100)
            readiness = evaluate_entry_readiness(
                has_indicators=bool(researched_candidate.get("has_indicators")),
                hard_blocked=bool(researched_candidate.get("hard_blocked")),
                entry_score=_safe_float(researched_candidate.get("final_entry_score", 0)),
                buy_score=_safe_float(researched_candidate.get("final_entry_score", 0)),
                sell_score=_safe_float(sell_score, 100.0),
                gate_level=gate_level,
                min_entry_score=min_entry_score,
                max_sell_score=max_sell_score,
                gating_notes=list(researched_candidate.get("quant_notes") or []),
                market_research_blocked=bool(researched_candidate.get("market_research_blocked"))
                or researched_candidate.get("gpt_action_hint") == "block_entry",
            )
            researched_candidate.update(readiness)
            researched_candidate["should_trade"] = bool(readiness["entry_ready"])
            researched_candidates.append(researched_candidate)

        def final_candidate_sort_key(row: dict[str, object]):
            symbol = str(row.get("symbol", "")).upper()
            return (
                0 if bool(row.get("entry_ready")) else 1,
                -_safe_float(row.get("final_entry_score", 0)),
                _safe_float(row.get("quant_sell_score", 100), 100.0),
                -_safe_float(row.get("market_confidence", 0), 0.0),
                _risk_rank(row.get("event_risk")),
                _risk_rank(row.get("news_risk")),
                _risk_rank(row.get("macro_risk")),
                0 if bool(row.get("has_indicators")) else 1,
                watchlist_order_map.get(symbol, len(watchlist_order_map)),
            )

        final_candidates = sorted(researched_candidates, key=final_candidate_sort_key)
        final_ranked_candidates = final_candidates
        final_best_candidate = final_candidates[0] if final_candidates else None
        second_final_candidate = final_candidates[1] if len(final_candidates) > 1 else None
        final_score_gap = round(
            float(final_best_candidate.get("final_entry_score", 0))
            - float(second_final_candidate.get("final_entry_score", 0))
            if second_final_candidate
            else 0.0,
            2,
        )
        candidate_symbol = final_best_candidate["symbol"].upper() if final_best_candidate else None
        best_score = _safe_float(final_best_candidate.get("final_entry_score", 0)) if final_best_candidate else 0.0

        tied_final_candidates = [
            {"symbol": candidate.get("symbol"), "final_entry_score": _safe_float(candidate.get("final_entry_score", 0))}
            for candidate in final_candidates
            if _safe_float(candidate.get("final_entry_score", 0)) == best_score
        ]
        near_tied_candidates = [
            {"symbol": candidate.get("symbol"), "final_entry_score": _safe_float(candidate.get("final_entry_score", 0))}
            for candidate in final_candidates
            if abs(best_score - _safe_float(candidate.get("final_entry_score", 0))) <= 1.0
        ]
        tie_breaker_applied = len(tied_final_candidates) > 1 or len(near_tied_candidates) > 1

        svc = TradingOrchestratorService()
        parent_run_key = f"watchlist_{uuid.uuid4().hex[:12]}"
        request_payload = {
            "source_endpoint": source_endpoint,
            "watchlist_analysis": analysis,
            "researched_candidates": researched_candidates,
            "final_best_candidate": final_best_candidate,
        }
        if scheduler_slot:
            request_payload["scheduler_slot"] = scheduler_slot
        parent_run_log = svc._create_run_log(
            db,
            run_key=parent_run_key,
            trigger_source=trigger_source,
            symbol=candidate_symbol or "WATCHLIST",
            mode="watchlist_trade_trigger",
            gate_level=gate_level,
            stage="orchestration",
            result="pending",
            reason="watchlist_run_started",
            request_payload=request_payload,
        )

        trigger_block_reason = None
        sell_score_value = None
        if final_best_candidate is not None:
            sell_score_value = final_best_candidate.get("sell_score")
            if sell_score_value is None:
                sell_score_value = float(final_best_candidate.get("quant_sell_score", 100))

        should_trade = False
        if not final_best_candidate:
            trigger_block_reason = "no_best_candidate"
        elif not bool(final_best_candidate.get("entry_ready")):
            trigger_block_reason = str(final_best_candidate.get("block_reason") or "no_entry_ready_candidate")
        elif float(final_best_candidate.get("final_entry_score", 0)) < min_entry_score:
            trigger_block_reason = "final_score_below_min_entry"
        elif float(final_best_candidate.get("quant_score", 0)) < min_quant_score:
            trigger_block_reason = "quant_score_too_low"
        elif float(final_best_candidate.get("market_research_score", 0)) < min_research_score:
            trigger_block_reason = "research_score_too_low"
        elif final_score_gap < min_score_gap:
            trigger_block_reason = "weak_final_score_gap"
        elif not bool(final_best_candidate.get("has_indicators")):
            trigger_block_reason = "missing_indicators"
        elif final_best_candidate.get("event_risk") == "high":
            trigger_block_reason = "high_event_risk"
        elif final_best_candidate.get("gpt_action_hint") == "block_entry":
            trigger_block_reason = "gpt_blocked_entry"
        elif sell_score_value is not None and sell_score_value > max_sell_score:
            trigger_block_reason = "sell_pressure_too_high"
        else:
            should_trade = True

        if not final_best_candidate:
            final_candidate_selection_reason = "No final candidate was available after research scoring."
        elif tie_breaker_applied:
            final_candidate_selection_reason = (
                f"{candidate_symbol} selected after tie-breaker ordering; "
                f"best_score={best_score:.2f}, final_score_gap={final_score_gap:.2f}, "
                f"min_score_gap={float(min_score_gap):.2f}."
            )
        else:
            final_candidate_selection_reason = (
                f"{candidate_symbol} selected with highest final_entry_score={best_score:.2f} "
                "and clear separation from other researched candidates."
            )

        result = {
            "watchlist_source": analysis["watchlist_source"],
            "configured_symbol_count": analysis["configured_symbol_count"],
            "analyzed_symbol_count": analysis["analyzed_symbol_count"],
            "max_watchlist_size": analysis["max_watchlist_size"],
            "watchlist": analysis["watchlist"],
            "quant_candidates_count": len(quant_candidates),
            "researched_candidates_count": len(researched_candidates),
            "top_quant_candidates": top_quant_candidates,
            "researched_candidates": researched_candidates,
            "final_ranked_candidates": final_ranked_candidates,
            "final_best_candidate": final_best_candidate,
            "second_final_candidate": second_final_candidate,
            "tied_final_candidates": tied_final_candidates,
            "near_tied_candidates": near_tied_candidates,
            "tie_breaker_applied": tie_breaker_applied,
            "final_candidate_selection_reason": final_candidate_selection_reason,
            "final_score_gap": final_score_gap,
            "best_score": best_score,
            "min_entry_score": min_entry_score,
            "strong_entry_score": strong_entry_score,
            "min_score_gap": min_score_gap,
            "max_sell_score": max_sell_score,
            "should_trade": should_trade,
            "triggered_symbol": None,
            "trigger_block_reason": trigger_block_reason,
        }

        if not should_trade:
            trade_result = {
                "action": "hold",
                "risk_approved": False,
                "order_id": None,
                "reason": trigger_block_reason,
            }
            response_payload = {
                **analysis,
                "triggered_symbol": None,
                "should_trade": False,
                "trade_result": trade_result,
                "trigger_block_reason": trigger_block_reason,
                "quant_candidates_count": len(quant_candidates),
                "researched_candidates_count": len(researched_candidates),
                "top_quant_candidates": top_quant_candidates,
                "researched_candidates": researched_candidates,
                "final_ranked_candidates": final_ranked_candidates,
                "final_best_candidate": final_best_candidate,
                "second_final_candidate": second_final_candidate,
                "tied_final_candidates": tied_final_candidates,
                "near_tied_candidates": near_tied_candidates,
                "tie_breaker_applied": tie_breaker_applied,
                "final_candidate_selection_reason": final_candidate_selection_reason,
                "final_score_gap": final_score_gap,
                "best_score": best_score,
                "min_entry_score": min_entry_score,
                "strong_entry_score": strong_entry_score,
                "min_score_gap": min_score_gap,
                "max_sell_score": max_sell_score,
            }
            result["trade_result"] = trade_result
            result["run"] = svc._finish(
                db,
                parent_run_log,
                stage="done",
                result="skipped",
                reason=trigger_block_reason,
                response_payload=response_payload,
            )
            return result

        symbol = candidate_symbol
        position = svc.trading_service.broker.get_position(symbol)
        if position is not None:
            child_mode = "position_management"
            allowed_actions = ["hold", "sell"]
            enforce_entry_limits = False
        else:
            child_mode = ENTRY_SCAN_MODE
            allowed_actions = ["hold", "buy"]
            enforce_entry_limits = True

        child_result = svc._run_symbol_child(
            db,
            trigger_source=trigger_source,
            symbol=symbol,
            mode=child_mode,
            allowed_actions=allowed_actions,
            gate_level=gate_level,
            parent_run_key=parent_run_key,
            symbol_role="watchlist_candidate",
            enforce_entry_limits=enforce_entry_limits,
            request_payload={
                "final_best_candidate": final_best_candidate,
                "watchlist_source": analysis["watchlist_source"],
                "source": "watchlist_trigger",
            },
        )

        child_payload = child_result.get("response_payload") or {}
        risk_data = child_payload.get("risk") or {}
        trade_result = {
            "action": child_payload.get("action"),
            "risk_approved": bool(risk_data.get("approved", False)),
            "order_id": child_result.get("order_id"),
            "reason": child_payload.get("reason") or child_result.get("reason"),
        }
        response_payload = {
            **analysis,
            "triggered_symbol": symbol,
            "should_trade": should_trade,
            "trade_result": trade_result,
            "child_run": child_result,
            "trigger_block_reason": trigger_block_reason,
            "quant_candidates_count": len(quant_candidates),
            "researched_candidates_count": len(researched_candidates),
            "top_quant_candidates": top_quant_candidates,
            "researched_candidates": researched_candidates,
            "final_ranked_candidates": final_ranked_candidates,
            "final_best_candidate": final_best_candidate,
            "second_final_candidate": second_final_candidate,
            "tied_final_candidates": tied_final_candidates,
            "near_tied_candidates": near_tied_candidates,
            "tie_breaker_applied": tie_breaker_applied,
            "final_candidate_selection_reason": final_candidate_selection_reason,
            "final_score_gap": final_score_gap,
            "best_score": best_score,
            "min_entry_score": min_entry_score,
            "strong_entry_score": strong_entry_score,
            "min_score_gap": min_score_gap,
            "max_sell_score": max_sell_score,
        }

        result["trade_result"] = trade_result
        result["triggered_symbol"] = symbol
        result["run"] = svc._finish(
            db,
            parent_run_log,
            stage="done",
            result=child_result.get("result", "skipped"),
            reason="watchlist_trade_completed",
            response_payload=response_payload,
        )
        return result
