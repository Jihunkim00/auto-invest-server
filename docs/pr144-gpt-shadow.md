# PR144 Stop-Loss Aware GPT V2

The KIS `A_TOP5_C_GPT` Schedule uses legacy C 15m/30m and legacy GPT for production. The shadow worker evaluates the same Pattern A Top 5 with C 10m/30m, 60m trend context and two independent GPT horizon judgments. Shadow records carry no execution authority.

## Schedule and runtime settings

The existing profile POST and PUT endpoints accept the optional `gpt_analysis` section. Profile responses return it at the top level, in `settings` and in `effective_settings`. Existing profiles receive these defaults when read.

| Field | Default | Accepted values |
| --- | --- | --- |
| `gpt_scoring_mode` | `legacy` | `legacy` |
| `gpt_v2_shadow_enabled` | `true` | Boolean |
| `gpt_short_horizon_minutes` | 30 | Integer 1–119 |
| `gpt_long_horizon_minutes` | 60 | Integer 2–120, greater than short horizon |
| `gpt_event_lookahead_days` | 7 | Integer 0–30 calendar days |

The run snapshot uses effective profile exit settings. Profile percentages are percentage points. An effective stop of 2% is recorded as a magnitude of 0.02 and an effective target of 3% as 0.03. Existing KIS safety rules require both exits. The analysis includes the user scheduler's next same-session profile check or, for the independent admin lifecycle monitor, the estimated first check 30 minutes after a hypothetical fill. The latter depends on the actual fill timestamp and is labeled an estimate. Analysis horizons are checkpoints for the study.

The worker starts with FastAPI and uses these environment settings.

| Variable | Default | Runtime bound |
| --- | --- | --- |
| `KIS_GPT_SHADOW_WORKERS` | 2 | 1–8 concurrent runs |
| `KIS_GPT_SHADOW_QUEUE_SIZE` | 2 | 0–20 waiting runs |
| `KIS_GPT_SHADOW_DEADLINE_SECONDS` | 25 | 1–120 seconds from snapshot handoff |
| `KIS_GPT_SHADOW_KIS_CONCURRENCY` | 1 | 0–4 additional in-flight reads |
| `KIS_GPT_SHADOW_OPENAI_CONCURRENCY` | 1 | 0–4 additional in-flight calls |
| `KIS_GPT_SHADOW_CALENDAR_TTL_SECONDS` | 21600 | 60–86400 seconds |
| `KIS_GPT_SHADOW_MASTER_DIR` | Unset | Folder containing dated official KIS master files |
| `KIS_GPT_SHADOW_COST_BPS` | 0 | Estimated round-trip cost for outcome labeling |

Both branches reuse the ranked universe and the original quote, daily and one-minute stock reads. The bounded shadow queue receives an immutable serialization when legacy Pattern B has supplied the shared minute data and before legacy Pattern C starts. Legacy C and GPT continue immediately. The V2 worker uses separate SQLAlchemy sessions and separate KIS and OpenAI capacity. The KIS worker uses cached tokens, a minimum spacing of two seconds or twice the configured production read spacing, and zero retries. Additional calls are best effort when capacity is available. At most one shadow OpenAI call is issued per C-qualified candidate, for up to five candidates. Each call contains both horizons. The independent worker commits pending and terminal rows by observation key and uses the analysis deadline to discard late scores. V1 records its decision independently.

## Scoring and corporate events

For each horizon, Python applies weights of 30% stop-loss safety, 25% continuation, 15% entry and volatility, 15% profit potential, 10% sector and market, and 5% company events. The score is capped at 59 when stock-specific reversal evidence is missing, downside is high, or the core safety and reversal components fail. The combined GPT score is the lower horizon score. The advisory final is 75% experimental C and 25% combined GPT. The C, GPT and final gates remain 65, 60 and 65. The score describes the supplied evidence and carries no calibrated probability.

KIS Domestic Stock API 145 returns KSD dividend record dates, payment dates and reported cash dividend amounts. It supplies neither a publication timestamp nor an ex-dividend date. The cache timestamps first observation and a run uses calendar data observed by its decision. The existing admin watchlist refresh opportunistically prefetches the first five ranked symbols. Positive payment dates are neutral in the prompt. Structured events from `CompanyEvent` carry a verification flag based on source and explicit payload evidence. KIS disclosure titles can supply advisory context for dividend announcements, earnings and calls, shareholder meetings, offerings and bonus issues, splits and reverse splits, reductions, lock-up events, repurchases, cancellations, halts and resumptions. Titles alone have unknown event dates. Automatic structured ingestion for those types, dividend increase/decrease verification and direct OpenDART/KRX/KIND synchronization require additional source coverage.

KIS sector API `FHKUP03500200` uses stock-to-index mapping from the official KIS stock master files. Use `<master dir>/YYYY-MM-DD/kospi_code.mst` and `kosdaq_code.mst` with their original CP949 encoding and a file timestamp at or before the decision. Stock and index returns require exact shared minute timestamps. Additional market data retrieved after the decision carries its retrieval time and is excluded from strict comparison when the source is a live snapshot. Execution-strength and bid/ask evidence uses dated-session, as-of KIS time-of-trade responses. Minute-bar direction volume is a proxy for pressure. Executed buy/sell imbalance, order-book quantity, slippage estimates and time-of-day relative volume require additional data.

KIS supplies adjusted historical daily prices. For unadjusted inputs, an explicitly verified corporate action may provide a historical price multiplier, or a verified ex-date and dividend amount may support an analytical cash adjustment. Missing verification is surfaced in the data-quality fields. Intraday prices, entry references and hypothetical barriers use unadjusted price units.

Official references

- [KIS Domestic Stock API 145 request example](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/ksdinfo_dividend/ksdinfo_dividend.py)
- [KIS Domestic Stock API 145 response mapping](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/ksdinfo_dividend/chk_ksdinfo_dividend.py)
- [KIS sector minute-chart example](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_indexchartprice/inquire_time_indexchartprice.py)
- [KIS stock master file formats](https://github.com/koreainvestment/open-trading-api/tree/main/stocks_info)
- [KIS time-of-trade example](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_time_itemconclusion/inquire_time_itemconclusion.py)
- [KIS request limit announcements](https://apiportal.koreainvestment.com/docs)

## Storage and results APIs

The normal database initializer creates `kis_gpt_shadow_observations` on existing installations. It has a unique observation key consisting of the common run key and symbol. The row stores profile owner, decision timestamp, status and two versioned JSON documents for analysis and outcome. Legacy observation records remain available in their original schema.

Latest authorized results are available from `GET /strategy-profiles/{profile_id}/gpt-shadow` and `GET /users/me/automation-profiles/{profile_id}/gpt-shadow`. Both return `{"shadow_only":true,"items":[...]}`. The result includes legacy C/GPT/final and V2 scores when present. Status values are `pending`, `completed`, `partial`, `timeout`, `failed`, `unavailable`, and `skipped_capacity`. A run skipped before entering the worker is recorded in legacy diagnostics and the export.

## Outcomes and external ABC Analyzer

The existing quant outcome labeler adds one-minute price-path labels at both recorded horizons. It records theoretical first touch, stop survival, MFE and MAE, time to barriers, recovery and estimated net return. An opening print beyond a barrier wins over a later touch in the same candle. When both barriers are reached after the opening print, the label records ambiguity and an SL-first sensitivity. Simulated periodic exits use the latest completed minute close at the scheduled check. Actual broker execution requires explicit order lineage and remains null for these advisory observations. A missing minute or insufficient regular-session time receives an explicit status.

The existing exporter keeps legacy columns and appends five optional columns on a PR144 schema. The incoming JSON remains an array of rows. CSV uses empty cells for nulls. The nested columns are serialized JSON strings in both formats.

| Field | Meaning |
| --- | --- |
| `gpt_v2_export_version` | `pr144-v1` for PR144 observations |
| `gpt_v2_status` | Individual shadow status |
| `gpt_v2_analysis_json` | A rank and score, C versions and V2 score, V2 component scores, effective Schedule, corporate and sector context, missing inputs, timings, eligibility, strict-match flag |
| `gpt_v2_outcome_json` | `stop-loss-path-v1` with `short` and `long` checkpoint labels |
| `gpt_v2_v1_performance_json` | Production path timings and counts |

See the [JSON fixture](../app/tests/fixtures/pr144_abc_export.json) and [CSV fixture](../app/tests/fixtures/pr144_abc_export.csv). The standalone ABC Analyzer can continue reading existing columns. For PR144 analytics, read the five optional columns by name, parse embedded JSON, and join by `observation_key` or by the pair `run_key` and `symbol`. Keep empty and null scores as missing. Filter strictly matched comparisons using `strict_match_eligible` and require the scores needed by each comparison. Report coverage and separate strategy-specific eligibility, incomplete paths and missed analyses.

Use `--v2-summary path.json --evaluation-from YYYY-MM-DD` to designate a chronological holdout for the four score combinations. Keep the fixed gates for that holdout. The summary includes outcome sample sizes, candidate coverage, market regime and event coverage, and p50/p95 latency. Historical quote and corporate-event availability can limit strict coverage. Controlled fake-response latency tests demonstrate scheduling behavior. Production latency, API usage, costs and predictive performance require subsequent observations.
