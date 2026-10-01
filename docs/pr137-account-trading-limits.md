# PR137 — Account-scoped trading limits and admin-configurable exposure controls

브랜치: `pr137-account-trading-limits` · 기준 커밋: `e79c66d` (PR136).

KIS 자동 BUY의 공통 100만 원 상한을 제거하고, 계정별 총 보유 평가금액/종목별 보유 평가금액 한도로 변경했다. 일반 계정 기본값은 총 1,000만 원 / 종목당 100만 원이며 관리자 기본값은 두 항목 모두 `NULL`(제한 없음)이다. 프로필의 주문당 금액, 주문 가능 현금, 기존 위험 및 실행 안전장치는 계속 적용된다.

## 기존 문제와 제거한 경로

이전 `automation_profile_safety.py`는 `TEST4_HARD_SAFETY['max_order_notional_krw'] = 1_000_000.0`으로 프로필의 유효 주문금액을 낮췄다. DB에 300만 원을 설정해도 실행 설정은 100만 원이 되었다. `kis_automation_execution_core.py`는 별도의 `HARD_MAX_NOTIONAL_KRW = 1_000_000.0`으로 실주문의 최종 예산을 다시 제한했다.

연관 중복 제한도 다음 경로에서 제거했다.

- `strategy_profile_sizing_service.py`: 프로필/목표 예산과 별도로 적용하던 `hard_cap_limited`.
- `strategy_risk_budget_service.py`: 위험 예산의 공통 100만 원 구성요소.
- `compound_capital_service.py`: 복리 전략 예산을 공통 안전금액으로 제한하던 처리.
- `user_trading_execution_service.py`: 일반 사용자 자동매매 수량 계산의 공통 100만 원.
- `strategy_profile_service.py`: 누락된 커스텀 프로필 주문금액에 100만 원을 부여하던 fallback. 누락되면 금액 0으로 BUY를 차단한다.
- 위험/드라이런 스키마의 `hard_max_order_notional_krw`는 호환용 nullable 필드로 유지하며 값은 `None`이다. 주문 제한에 사용하지 않는다.

`TEST4_HARD_SAFETY`의 점수, 시간, 포지션 수, 현금 주문, TP/SL 관련 안전 규칙은 유지했다. Operation Test4의 독립 설정은 유지했다.

## DB와 계정 소유권

별도의 브로커 계정 테이블 대신 기존 canonical `User`와 `(user_id, provider)`가 유일한 `UserBrokerCredential` 구조를 사용했다. 자동매매 프로필 테이블에는 계정 한도를 추가하지 않았다.

`users`에 nullable Float 두 항목을 추가했다.

| 항목 | 의미 | 일반 계정 기본값 | 관리자 기본값 |
| --- | --- | ---: | --- |
| `account_max_total_exposure_krw` | 계정 전체의 현재 보유 평가금액 상한 | 10,000,000 | NULL |
| `account_max_position_notional_krw` | 한 종목의 현재 보유 평가금액 상한 | 1,000,000 | NULL |

`NULL`은 해당 차원을 `min()`에서 제외한다. 큰 숫자나 음수 sentinel을 사용하지 않는다. 명시적으로 저장한 일반 계정의 `NULL`도 ORM 기본값으로 덮어쓰지 않는다. 관리자도 유한 한도를 설정하면 그대로 적용되며 역할에 따라 실행 시 한도를 무시하지 않는다.

실행 판단은 canonical `role`과 정확한 owner를 사용한다. `username == 'admin'` 또는 `owner_user_id == 1`을 계정 한도 판단에 사용하지 않는다. 기존 환경 기반 관리자 주문의 NULL owner 경로는 관리자 역할로만 해석하며 일반 계정의 fallback으로 사용하지 않는다. 일반 계정은 owner/provider/market 및 내부 계정 식별자를 확인한다. 내부 식별자는 `admin:kis:KR` / `user:{id}:kis:KR`이며 실제 계좌번호를 포함하지 않는다.

추가 테이블:

- `account_trading_limit_audits`: 대상 owner/내부 계정 ID, 두 한도의 변경 전후 값, 변경자, 시각.
- `account_buy_execution_claims`: 계정 ID를 DB primary key로 사용하는 자동 BUY 실행 잠금.

## 마이그레이션

`init_db()`에서 기존 관리자 bootstrap 조회보다 먼저 additive migration을 실행한다. 기존 SQLite users 테이블에는 누락된 열만 추가하고, 동일 트랜잭션에서 역할에 따라 관리자 NULL/NULL, 일반 계정 10M/1M을 채운다. SQLite는 `BEGIN IMMEDIATE`로 DDL과 backfill을 묶는다.

재실행 시 이미 있는 열은 갱신하지 않아 관리자가 설정한 값과 명시적 NULL을 보존한다. 기존 프로필 `capital.max_order_notional_krw`를 수정하지 않는다. 새 계정의 ORM 기본값도 역할에 따라 설정한다. 이 작업 중 운영 DB에 마이그레이션을 실행하지 않았으며 테스트는 격리 DB에서 수행했다.

## 공통 BUY 계산

`app/services/account_trading_limit_service.py`가 계정 해석, 노출 계산, 유효 BUY 예산, 계정 잠금을 담당한다. 드라이런/위험 분석/스케줄러/guarded BUY/실주문이 같은 계산을 사용한다.

```text
현재 계정 노출 = Σ(각 보유 종목의 현재가 × 보유 수량)
현재 종목 노출 = 후보 종목의 현재가 × 보유 수량

종목 잔여 = max(0, 종목 한도 − 현재 종목 노출 − 해당 종목 미반영 BUY 예약)
계정 잔여 = max(0, 총 한도 − 현재 계정 노출 − 전체 미반영 BUY 예약)

기본 BUY 예산 = min(적용되는 유한 항목)
  프로필 주문당 한도
  프로필 비율 한도 또는 명시적 전략 진입 예산
  종목 잔여
  계정 잔여
  새로 조회한 주문 가능 현금

유효 BUY 예산 = 기본 BUY 예산 × 기존 위험 축소 배율(0~1)
주문 수량 ≤ floor(유효 BUY 예산 / 현재가)
```

한도가 NULL인 차원은 잔여 계산과 최솟값에서 제외한다. 프로필 설정값은 유지하며 유효 금액과 제한 원인을 별도로 반환한다. 기존 전략 예산과 비율/복리 규칙도 남아 있다.

현재가가 없거나 0이면 신뢰할 수 있는 현재 평가금액을 사용할 수 있다. 평균 매입원가는 노출 계산에 사용하지 않는다. 같은 종목의 동일 행은 한 번만 계산하고, 서로 모순된 중복 행이나 누락/음수/비유한 수량·평가금액은 BUY를 차단한다. 브로커 정규화 과정에서 잘못된 수량이 빈 포트폴리오로 보이지 않도록 `positions_reliable`을 확인한다.

주문 예약은 owner/provider/market 범위로 한정한다. REQUESTED/SUBMITTED/ACCEPTED/PENDING/PARTIALLY_FILLED/UNKNOWN_STALE 주문의 미반영 금액을 보수적으로 차감한다. 부분 체결 중 이미 보유에 반영된 수량은 이중 계산하지 않는다. 신규 정책으로 저장한 FILLED 주문도 보유 반영이 늦으면 저장한 제출 전 수량을 기준으로 아직 보이지 않는 수량을 예약한다. 포지션 lifecycle이 종료된 경우 이 예약을 해제한다.

예: 관리자 프로필 300만/현금 200만은 최대 200만 원, 일반 계정 프로필 50만은 최대 50만 원, 종목 70만 보유/종목 한도 100만은 최대 30만 원, 총 960만 보유/총 한도 1,000만은 최대 40만 원이다. 기존 위험 배율이 0.5이면 최솟값을 구한 후 다시 절반으로 축소한다.

## 최종 실행, 동시성, SELL

실제 자동 KIS BUY는 계정 DB 잠금 안에서 owner/계정, 보유, 주문 가능 현금, 계정 한도, 관련 프로필과 위험 예산을 다시 읽고 재계산한다. 앞 단계의 승인 수량보다 수량을 늘리지 않는다. possible-order 응답의 시각과 실제 경과시간을 확인하여 제출 직전 10초를 넘으면 차단한다. 미확인 브로커 POST 결과는 UNKNOWN_STALE로 남겨 노출 예약을 보존하며 POST를 재시도하지 않는다.

계정 한도 변경 API도 동일한 잠금을 사용하므로 BUY와 설정 변경이 동시에 기존 한도를 소비하지 않는다. 다른 계정의 잠금/설정/예약에는 영향을 주지 않는다.

계정 잠금 보유 중 프로세스가 종료되면 잠금은 만료로 자동 해제하지 않고 BUY를 차단한다. 이 경우 브로커 주문 및 DB 주문 상태를 먼저 대조한 뒤 운영자가 잠금을 복구해야 한다. 불확실한 주문을 자동으로 재제출하지 않기 위한 제한이다.

새 계정 한도는 BUY/노출 확장에 적용한다. 보유금액이 한도를 넘거나 한도를 현재 보유 이하로 낮춰도 SELL/EXIT를 막지 않는다. held-position-first/SELL-first, 1분 간격 최대 3회 SELL 재시도, transient KIS read 재시도, TP/SL, 브로커 POST 재시도 금지는 유지했다.

최소 진입 점수 65, cash-only, 최대 포지션, 중복/예약/idempotency, 일일 거래 상한, 시장 세션/컷오프, 손실 제한/kill switch, execution authority를 완화하지 않았다.

## 관리자 API와 감사

기존 `/admin/users` API에 상세와 한도 관리 기능을 확장했다. 모든 신규 endpoint는 `require_admin`을 사용한다.

| 메서드/경로 | 동작 |
| --- | --- |
| `GET /admin/users/{user_id}` | 기존 사용자 상세 + `trading_limits` |
| `PUT /admin/users/{user_id}/trading-limits` | 두 한도를 함께 수정하고 감사 기록 |
| `GET /admin/users/{user_id}/trading-limits/usage` | 신뢰할 수 있는 현재 총/최대 종목 노출과 총 잔여 표시 |

읽기 필드: `max_total_exposure_krw`, `max_position_notional_krw`, `total_exposure_unlimited`, `position_notional_unlimited`, 내부 계정 ID/provider/market.

```json
{"max_total_exposure_krw": 10000000, "max_position_notional_krw": 1000000}
```

```json
{"max_total_exposure_krw": null, "max_position_notional_krw": null}
```

유한 값은 양수/finite이어야 하며 두 필드가 모두 필요하다. 추가 필드는 거부한다. 동일 값 재전송은 중복 감사 기록을 만들지 않는다. 한도 변경과 감사 기록은 같은 commit으로 저장한다. 일반 사용자는 자기 설정 API로 이 필드를 변경할 수 없다.

사용 현황은 설정과 분리되어 있다. owner/provider/market/계정 ID 불일치, 보유 불확실, 브로커 오류는 `available: false` / `account_exposure_state_unavailable`로 응답하며 설정 조회/편집은 계속 가능하다. broker key/token/계좌번호/원본 오류는 설정, 사용 현황, 감사 기록에 노출하지 않는다. KIS sanitizer는 안전한 정책 숫자/NULL/구조를 유지하면서 비밀 값은 계속 마스킹한다.

## Flutter

기존 관리자 계정 활성/관리 목록에서 계정을 누르면 `계정 상세 설정 → 거래 한도`로 이동한다. 새 최상위 메뉴를 만들지 않았다. 기존 계정 활성 스위치는 그대로 사용한다.

- `계정 총 투자 한도`, `종목당 최대 금액`에 원화 쉼표 표기.
- 각 항목의 `제한 없음` 스위치가 입력을 비활성화하고 NULL을 저장.
- 일반 계정 기본 10M/1M 및 관리자 제한 없음 표시.
- 유한 값은 숫자로 전송하고 저장 실패 시 마지막 서버 설정으로 복구.
- 새로고침 GET으로 서버 값을 재적용하고 계정 간 화면 상태를 분리.
- 비관리자 bootstrap에서는 관리/편집 기능에 진입하지 못하도록 기존 패널 연결에서 제한.
- 현재 총 투자금액/총 잔여/최대 종목 사용량은 별도 조회 상태로 표시. 사용량 오류가 설정 화면을 실패시키지 않는다.

PR136 bootstrap/controller와 일반 사용자 account-load retry 코드는 변경하지 않았다.

## 남아 있는 금액 상수 전수 분류

요청된 패턴으로 app의 모든 Python 파일을 검색하여 198개 일치 행을 개별 분류했다. 전체 위치/원문/분류는 [상수 전수 점검](pr137-account-trading-limit-constant-audit.md)에 있다.

| 분류 | 일치 행 수 | 처리 |
| --- | ---: | --- |
| 일반 계정 종목 한도 1M 기본값 | 2 | 새 정책의 명시적 기본값 |
| Operation Test4 독립 주문/가격 cap | 39 | 별도 안전 설정 유지 |
| 기존 점수/세션/포지션/TP/현금 안전 규칙 | 11 | 금액 ceiling만 제거 |
| nullable 호환 telemetry | 8 | 제한으로 사용하지 않음 |
| 시장 데이터 단위 변환 | 1 | 투자자 흐름의 백만 단위 변환 유지 |
| Agent Chat 독립 설정 검증 상한 | 1 | 실제 10M 상한의 부분 문자열 일치; 유지 |
| 격리 테스트 fixture/모의 현금/정책 검증 값 | 136 | 테스트 목적 금액 유지 |

`HARD_MAX_NOTIONAL_KRW` 또는 모든 계정 자동 BUY를 제한하는 TEST4 1M은 남아 있지 않다. `kis_max_manual_order_amount_krw`, `agent_chat_live_order_max_notional_krw`의 설정/독립 제한을 변경하지 않았다.

## 추가/수정 테스트와 최종 검증

새 백엔드 정책 테스트: `app/tests/test_account_trading_limits_pr137.py` 65개. 역할별 신규 기본값/명시적 NULL, 기존 DB backfill/재실행/프로필 보존, 공식의 각 제한 원인/위험 배율, 중복 보유/불확실 상태, 계정 격리, 관리자 권한/API 감사/NULL, 실 BUY의 새 한도·프로필·현금·보유 재확인, 동시 잠금/예약/부분 체결/보유 반영 지연, SELL, 비밀 마스킹, 사용량 신뢰도와 계정 범위를 검증한다.

기존 자동매매 테스트는 제거된 공통 1M에 대한 기대값을 실제 프로필 한도로 바꾸고, fake 브로커에 신뢰할 수 있는 현금/보유/현재가를 추가했다. 수량/중복/실행/SELL 안전 검증을 약화하지 않았다. Alpaca 테스트 및 별도 수동 주문/Agent Chat 설정 코드는 변경하지 않았다.

새 Flutter 테스트: `test/admin_account_trading_limits_test.dart` 12개. 상세 진입, 기본값/무제한 표시, toggle와 NULL/숫자 저장, 실패 복구, refresh, 계정 간 독립, 비관리자 접근 제한, 기존 활성 toggle, 사용량 조회 실패를 검증한다.

| 검증 | 결과 | 로그 |
| --- | --- | --- |
| 전체 백엔드 `python -m pytest -q` | 2,105 passed (1321.85초) | `artifacts/pr137/backend-final.txt` |
| 필수 scheduler/lifecycle replay + 새 정책 테스트 | 123 passed (정책 65 + 필수 replay 58) | `artifacts/pr137/policy-replays-final.txt` |
| Flutter 전체 test | 749 passed | `artifacts/pr137/flutter-final.txt` |
| Flutter analyze | No issues found | `artifacts/pr137/flutter-analyze-final.txt` |
| `python -m compileall app` | 통과 (exit 0) | `artifacts/pr137/compileall.txt` |
| `git diff --check` | 통과 (exit 0) | `artifacts/pr137/diff-check-final.txt` |

테스트는 격리 DB와 FakeBroker/FakeKisClient 및 HTTP mock을 사용했다. 실제 KIS 브로커 주문은 제출하지 않았다. 시장 regime 계산/스케줄러, AI/GPT/quant/C-score 및 BUY/SELL 점수 임계값, 전략 거래 빈도, PR136 bootstrap/retry, SELL retry, 수동 주문/Agent Chat의 독립 한도는 변경하지 않았다.

## 변경 파일

- `app/db/init_db.py`
- `app/db/models.py`
- `app/routes/users.py`
- `app/schemas/strategy_dry_run_auto_buy.py`
- `app/schemas/strategy_risk.py`
- `app/schemas/user_data.py`
- `app/services/account_trading_limit_service.py`
- `app/services/automation_profile_buy_scheduler_service.py`
- `app/services/automation_profile_safety.py`
- `app/services/compound_capital_service.py`
- `app/services/kis_automation_execution_core.py`
- `app/services/kis_payload_sanitizer.py`
- `app/services/profile_aware_dry_run_auto_buy_service.py`
- `app/services/strategy_profile_service.py`
- `app/services/strategy_profile_sizing_service.py`
- `app/services/strategy_risk_budget_service.py`
- `app/services/target_aware_risk_service.py`
- `app/services/user_broker_account_service.py`
- `app/services/user_trading_execution_service.py`
- `app/tests/test_account_trading_limits_pr137.py`
- `app/tests/test_agent_chat_live_order_service.py`
- `app/tests/test_automation_profiles.py`
- `app/tests/test_kis_automation_execution_core.py`
- `app/tests/test_pr110_fixed_budget_sizing.py`
- `app/tests/test_strategy_live_auto_buy_service.py`
- `app/tests/test_target_aware_risk_service.py`
- `app/tests/test_user_automation_profile_sizing_pr129.py`
- `docs/pr137-account-trading-limit-constant-audit.md`
- `docs/pr137-account-trading-limits.md`
- `lib/core/network/api_client.dart`
- `lib/features/admin/admin_account_detail_screen.dart`
- `lib/features/admin/admin_screen.dart`
- `lib/features/admin/admin_user_management_panel.dart`
- `test/admin_account_trading_limits_test.dart`

main 전환/병합, PR136 rebase/이력 수정, commit/push/PR 생성은 수행하지 않았다. 변경은 로컬 작업 트리에 남아 있다.
