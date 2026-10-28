# PR140 — 2026-10-28 운영 기록 기반 재현 보고

## 판정과 검증 범위

**저장된 분석 결과를 이어받는 스케줄러·게이트·리스크·주문 수명주기 재현은 PASS입니다. 원시 OHLCV부터 C를 다시 산출하는 완전한 역사 재현은 NOT REPRODUCIBLE, 실패 스냅샷의 제한된 자동 재시도는 NOT IMPLEMENTED입니다.** 이 세 가지를 같은 성공으로 계산하지 않습니다.

운영 코드와 설정 파일은 수정하지 않았습니다. 이전 PR140 합성 harness를 import하지 않는 독립 테스트 16개를 추가했습니다. 원본을 SQLite backup API로 복사하고, 테스트 복제본에서만 11:20 이후 주문·예약·신호·분석·슬롯을 제거하여 시작 직전 상태를 복원했습니다. 원본 주문 18번을 이용한 단순 중복 차단으로 테스트를 끝내지 않았습니다.

실제 `SchedulerSlotDispatcher`, `SchedulerTaskSupervisor`, `AutomationSchedulerService`, `UserAutoTradingSchedulerService`, 프로필 워치리스트 구성, C/GPT 게이트, `KisPreviewGptAdvisor` 응답 정규화, Final 혼합·정렬, `TargetAwareRiskService`/`StrategyRiskBudgetService`, `KisOrderValidationService`, `KisAutomationExecutionCore`와 DB 상태 전이를 사용했습니다. 저장된 지표로 선택 종목 A와 Final을 재계산해 저장 값과 일치하는 것도 확인했습니다.

`RecordedPreview`는 누락된 OHLCV를 만들어 내지 않고 DB의 runtime A/C 결과를 전달하는 분석 결과 어댑터입니다. 따라서 C 계산과 전체 원시 Quant 파이프라인을 재실행했다고 주장하지 않습니다. GPT 출력 점수·confidence·완료 상태는 DB에서 복원하고 실제 응답 처리 서비스를 거칩니다. 원문 GPT JSON과 원시 KIS HTTP 응답 전체는 보관돼 있지 않습니다. 설명문과 인증 자료는 테스트 결과에 저장하지 않습니다. 당시 미리보기의 `entry_ready=false`와 위험 경고도 보존하며 실행 허용 여부는 실제 canonical 게이트와 리스크 서비스가 판단합니다.

## 복원한 계정 조건

| 항목 | admin | test01 |
|---|---|---|
| 사용자 / 선택 프로필 ID | 1 / 5 | 2 / 8 |
| 분석 시간 KST | 11:20, 12:20, 13:30 | 11:30, 12:45, 13:45 |
| 기록된 현금·자산 | 300,598원 | 52,480원 |
| 자본 방식 / 고정 예산 | fixed_budget / 290,000원 | fixed_budget / 50,000원 |
| 프로필 주문 상한 | 290,000원 | 48,000원 |
| 복리 | realized_pnl, 활성 | realized_pnl, 활성 |
| 신규 진입 / 보유 상한 | 일 1건 / 1종목 | 프로필 일 1건 / 1종목; 사용자 설정 일 2건 |
| 신규 진입 마감 | 14:00 | 14:00 |
| SL / TP | 2% / 4% | 2% / 5% |
| 시작 전 미해결 주문 | 없음 | 주문 13번 UNKNOWN_STALE, 실제 체결 수량 0 |

프로필 마지막 수정 시각은 각각 10월 26일과 27일입니다. 모든 설정의 과거 버전이 보관된 것은 아니므로, 현재 DB의 해당 프로필이 당시 로그와 대응한다는 범위에서 복원했습니다. 계좌번호·키·토큰·비밀번호는 출력하지 않았습니다. 복제본의 인증 토큰·비밀번호·암호화된 사용자 인증 내용도 테스트 진입 전에 제거/비식별 처리했습니다. 실제 자동매매 프로세스를 시작하거나 원본 실거래 설정을 활성화하지 않았습니다.

## A — 관리자 11:20 정상 경로

| 계정 / 슬롯 | A / C / GPT / Final | AI | Risk | Buy window | Fake submit | 주문 / 예약 | 체결 / 미해결 | 판정 |
|---|---|---|---|---|---:|---|---|---|
| admin 11:20 | 72 / 69.09 / 61 / 67.07 | BUY | 승인 | 11:23 허용, 원래 마감 11:30 | 1 | FILLED / filled | 1 / 0 | PASS |

가상 시계는 11:20 시작 → 분석 완료 11:22:58 → 주문 생성 11:23:00으로 진행합니다. 036460 **7주**가 실제 실행 코어를 거쳐 FakeBroker에 정확히 한 번 전달되고 `FAKE-REPLAY-…` 접수번호가 저장됩니다. 체결은 FakeBroker의 명시적인 `filled`, 수량 7 응답으로 결정합니다. 실제 KIS 제출은 0회입니다. C65/GPT60/Final65, 시장·마감·권한·계좌 범위·현금·수량·주문가능금액 신선도·일일 한도를 완화하지 않았습니다.

## B — 제출 전 실패와 불확실한 제출

다음 7개 경우 모두 FakeBroker 호출 0, 주문 `REJECTED_BY_SAFETY_GATE`, 예약 `blocked`, `broker_submit_called=false`, `real_order_submitted=false`, 실제 체결 0, 미해결 점유 0, REQUESTED 잔류 0을 확인했습니다.

| 주입한 외부 조건 | 관측된 슬롯/차단 reason_code | 판정 |
|---|---|---|
| 11:31까지 지연 | scheduler_task_expired_before_buy | PASS |
| 주문 전 kill switch | global_kill_switch_enabled | PASS |
| 새 계좌 조회 실패 | account_snapshot_unavailable | PASS |
| 주문 검증용 시세 누락 | invalid_order | PASS |
| 제출 직전 시장 닫힘 | market_session_closed | PASS |
| 14:00 신규 진입 제한 도달 | scheduler_task_timeout | PASS |
| POST 이전 주문가능금액 준비 실패 | pre_submit_safety_blocked | PASS |

14:00 실험은 실제 11:20 슬롯을 유지하므로 10분 BUY 기한과 12분 작업 제한도 이미 지났습니다. 주문은 검증/안전 게이트에서 거절되고 슬롯 최종 사유는 작업 시간 초과가 됩니다. 마감 조건만 단독으로 분리하기 위해 실제 시간표나 마감 정책을 변경하지 않았습니다.

FakeBroker가 호출된 후 timeout으로 접수 결과가 불확실한 경우는 별도 C3에서 `UNKNOWN_STALE`/예약 `sync_required`, 중복 매수 차단 유지로 확인합니다. 이를 미제출 확정으로 바꾸지 않습니다.

## C — 12:20 두 번째 슬롯

재생한 두 번째 분석은 A=72, C=76.49, GPT=61, Final=72.62입니다. 표의 체결 수는 그 시점 하루 누적이며, 신규 호출은 해당 슬롯의 증가분입니다.

| 첫 슬롯 결과 | 12:20 직전 실제 체결 | 12:20 이후 실제 체결 | 미해결 점유 | 12:20 Fake 신규 호출 | 12:20 결과 / reason_code | 판정 |
|---|---:|---:|---:|---:|---|---|
| C1 FILLED | 1 | 1 | 0 | 0 | 기존 보유 유지, no_exit_trigger; 추가 BUY 없음 | PASS |
| C2 브로커 미호출 확정 차단 | 0 | 1 | 0 | 1 | 7주 FILLED, buy_filled | PASS |
| C3 접수 여부 불확실 | 0 | 0 | 1 | 0 | 기존 UNKNOWN_STALE 유지, unresolved_entry_limit_hit | PASS |
| 추가: 정상 접수·미체결 | 0 | 0 | 1 | 0 | 기존 SUBMITTED 유지, unresolved_entry_limit_hit | PASS |

미체결이라는 이유로 미확인 위험을 해제하지 않으며, 확정 미제출 주문만 실제 횟수와 미해결 점유에서 제외합니다. 원본의 12:20 `daily_trade_limit_hit`을 그대로 응답으로 주입하지 않고, 실제 Risk Engine이 복제본의 새 상태를 다시 평가합니다.

## D — 스냅샷 229와 복구 범위

| ID | 실제 시작 / 완료 KST | 상태 | scored / source | errors |
|---|---|---|---|---:|
| 227 | 10:50:09 / 10:53:30 | success | 200 / 200 | 0 |
| 228 | 11:50:01 / 11:53:22 | success | 200 / 200 | 0 |
| 229 | 12:50:07 / 12:53:37 | failed | 200 / 200 | 1 |
| 230 | 13:50:08 / 13:53:29 | success | 200 / 200 | 0 |

13:30 admin은 `watchlist_snapshot_not_ready`로 차단됩니다. 13:45 test01은 저장된 운영 기록과 동일하게 최상위 `user_scheduler_processing_failed`, 내부 `SchedulerTaskExpired`, 원인 `watchlist_snapshot_not_ready`로 차단됩니다. 두 계정에서 분석·신규 제출은 실행되지 않습니다. 이는 **fail-closed PASS**입니다.

**정확한 실패 종목/HTTP 오류는 NOT REPRODUCIBLE입니다.** 229의 200개 항목 모두 산출 지표를 가지고 있지만, 개별 `quote_error`/`daily_error` 메시지나 오류 종목이 DB에 보관되지 않았고 운영 로그에도 해당 시간의 집계 완료 메시지만 있습니다. 현재 `_build_item()` 경로에서 `scored_count=200, error_count=1`은 시세 조회 오류 뒤 정상 일봉 지표로 대체된 경우와 일치합니다. 이를 당시 특정 종목의 일시 오류였다고 확정하지 않습니다.

**제한된 자동 재시도: NOT IMPLEMENTED.** 실제 `WatchlistSnapshotScheduler`의 bootstrap과 가상 13:25 반복을 실행해도 새 스냅샷은 생기지 않습니다. 마지막 성공 228은 2시간 이내이므로 bootstrap 재생성 대상이 아니며, 정상 다음 정기 갱신은 13:50입니다. 실제 230이 13:53에 준비된 뒤에도 Dispatcher가 지난 13:30/13:45 슬롯을 재생하지 않는 것을 확인했습니다.

별도의 조건부 실험에서는 **성공한 230의 기록 데이터가 13:25에 수신되었다고 가정**해 새 ID로 복제본에 추가했습니다. run·항목 수신 시각을 모두 동일한 가정 시각으로 옮기고 200개 지표의 유효성과 실제 A 계산을 확인했습니다. 실패 229의 상태와 error_count는 바꾸지 않았습니다. 이 경우 admin 13:30, test01 13:45 모두 분석 경로에 다시 진입합니다. 해당 오후의 C/GPT 입력·응답은 없어 각각 `no_gpt_completed_execution_candidate`, `no_gpt_completed_candidate`로 매수하지 않습니다.

이는 **준비성 게이트 재개 PASS**이며 실제 자동 복구나 새 OHLCV에서 전체 스냅샷을 생성한 성공이 아닙니다. 원시 데이터 입수·C 재계산의 역사 재현은 여전히 NOT REPRODUCIBLE입니다.

## E — 계정별 전체 6개 슬롯

이 표는 첫 admin 제출을 불확실 응답으로 만든 E 실험입니다. A의 정상 체결 실험과 독립된 복제본입니다. 주문 상태는 해당 슬롯 신규 주문 기준이며, 기존 미해결 주문은 점유 수로 구분합니다.

| 계정 | KST | 워치리스트 | A/C/GPT/Final | 최종 AI action | Risk | Buy window | Fake 신규 호출 | 신규 주문 | reason_code | 체결 | 미해결 | 판정 |
|---|---|---|---|---|---|---|---:|---|---|---:|---:|---|
| admin | 11:20 | 성공 | 72/69.09/61/67.07 | BUY | 승인 | 허용 | 1 | UNKNOWN | broker_submit_sync_required | 0 | 1 | PASS |
| test01 | 11:30 | 성공 | 72/62.76/—/— | HOLD | 미실행 | 허용 | 0 | NOT SUBMITTED | c_score_below_threshold | 0 | 1* | PASS |
| admin | 12:20 | 성공 | 72/76.49/61/72.62 | HOLD | 차단 | 허용 | 0 | NOT SUBMITTED | unresolved_entry_limit_hit | 0 | 1 | PASS |
| test01 | 12:45 | 성공 | 72/56.91/—/— | HOLD | 미실행 | 허용 | 0 | NOT SUBMITTED | c_score_below_threshold | 0 | 1* | PASS |
| admin | 13:30 | 실패 | — | 미실행 | 미실행 | 허용 | 0 | NOT SUBMITTED | watchlist_snapshot_not_ready | 0 | 1 | PASS |
| test01 | 13:45 | 실패 | — | HOLD/분석 실패 | 차단 | 허용 | 0 | NOT SUBMITTED | user_scheduler_processing_failed → watchlist_snapshot_not_ready | 0 | 1* | PASS |

`*` test01의 1건은 원래 존재하던 주문 13번입니다. 관리자 주문이 생기기 전후 모두 1건이고 실제 체결 횟수는 0으로 유지됩니다. 주문 13번을 정리하거나 관리자 주문을 test01에 합산하지 않았습니다.

별도의 실제 병렬 lane 실험은 admin을 분석 중에 멈춘 채 test01 11:30을 먼저 완료한 뒤, 가상 시계를 admin의 12분 작업 제한까지 진행합니다. test01은 C 기준 미달 HOLD로 정상 종료하고 admin은 `scheduler_task_timeout`으로 종료합니다. 뒤늦은 FakeBroker 제출과 REQUESTED 잔류는 없습니다. 테스트 DB의 journal mode와 Session autoflush/timeout은 운영 설정을 유지했습니다. 실제 시간을 10분/12분 기다리지 않습니다.

## 원본 보호와 테스트 증거

- source connection은 SQLite `mode=ro`, `PRAGMA query_only=ON`; 일관된 backup API 사용.
- 모든 상태 재구성·가상 주문·인증 비식별 처리는 테스트 전용 복제본에 한정.
- requests/httpx, 직접 연결, 실제 KIS 제출·취소, 사용자 KIS 제출, Alpaca 제출 함수를 차단.
- 시나리오별 외부 HTTP, 실제 KIS, 실제 Alpaca 제출 카운터는 모두 0.
- 원본 파일 SHA-256과 주요 14개 테이블 전체 내용 해시/건수를 테스트 전후 비교해 동일함을 확인.
- 원본 주문/신호/run/예약/슬롯 건수는 각각 **18 / 94 / 268 / 10 / 45**로 동일. 원본 주문 18번 상태도 수정하지 않음.
- 원본 SHA-256 전후: `0cbfda0d1bf5a54ca7b868bd2517860690fda4dc7bc5e9d95638edbcf01fc521`로 동일.

비식별 시나리오 JSON과 테이블별 무결성 확인은 `.tmp/pr140-production-replay/`에 생성됩니다. 복제 DB는 pytest 임시 디렉터리에만 두고 보고서나 저장소에 포함하지 않습니다. 원본 토큰·비밀번호·계좌번호는 출력/결과물에 포함하지 않습니다.

## 검증 결과

| 검증 | 결과 |
|---|---|
| 신규 운영 기록 재현 | 16 PASS |
| 신규 + 기존 PR140 + 필수 scheduler/lifecycle replay | 111 PASS |
| 전체 backend pytest | 2,751 PASS, 496.48초, 실패/skip 0 |
| Flutter analyze | PASS, No issues found |
| Flutter test | 783 PASS |
| compileall / git diff --check | PASS |
| 실제 KIS / Alpaca 주문, 원본 DB 변경 | 0 / 0 / 0 |
| 자동 스냅샷 재시도 기능 | NOT IMPLEMENTED |
| 원시 OHLCV → C 재계산 / 개별 229 오류 특정 | NOT REPRODUCIBLE |

전체 backend는 작업 폴더의 기존 임시 pytest-xdist 설치 경로를 PYTHONPATH로 지정하고 `python -m pytest app/tests -q -p no:cacheprovider -n 8 --dist worksteal --maxfail=1`로 검증합니다. 새 프로젝트 의존성이나 운영 설정 변경은 없습니다. 생산 DB가 없는 환경에서는 이 신규 재현 테스트를 NOT REPRODUCIBLE로 skip하며 합성 데이터 통과로 대체하지 않습니다.

최종 backend에는 deprecated API·중복 OpenAPI operation ID·SQLite datetime adapter 관련 경고 61개가 있습니다. 테스트 실패는 없습니다.

## 질문별 답변과 후속 수정안

1. **11:20과 같은 점수·안전 조건이면 11:23에도 모의 매수가 실행되는가?** 예. 위 기록 재생 범위에서 실제 실행 코어와 FakeBroker 1회/7주/FILLED까지 확인했습니다. 원시 C 산출까지 같은 시장 입력으로 검증한 것은 아닙니다.
2. **11:20 확정 미제출이면 12:20을 불필요하게 막는가?** 아니오. 실제 체결·미해결 점유가 0이 되고 12:20의 72.62점 후보가 실제 리스크 재검사 후 모의 체결됩니다. 불확실한 제출은 보수적으로 계속 차단합니다.
3. **현재 코드가 229 실패를 제때 자동 복구하는가?** 아니오. 제한된 재시도는 구현되어 있지 않고, 실제 13:53 성공은 두 슬롯보다 늦습니다.
4. **별도 PR에서 고칠 위치는?** `app/services/watchlist_snapshot_service.py:WatchlistSnapshotService._build_item`에 비식별 종목별 오류 유형/단계 기록이 필요합니다. `app/services/watchlist_snapshot_scheduler.py:WatchlistSnapshotScheduler._run`, `_run_refresh`, `_bootstrap_if_needed`에 일시 오류 분류와 제한된 읽기 재시도·새 스냅샷 생성 정책을 추가하는 수정안을 제안합니다. failed를 success로 바꾸거나 error_count/신선도 검사를 무시하지 않아야 합니다. test01의 상위 오류도 구체화하려면 `UserAutoTradingSchedulerService`의 canonical processing 예외 기록 경로에서 `SchedulerTaskExpired` 원인을 상위 reason에 보존하는 별도 변경을 검토할 수 있습니다. 이번 단계에서는 운영 코드를 수정하지 않았습니다.
5. **실제 운용과 다른 가정은?** 원시 OHLCV 미보관으로 C는 저장 값 재생, GPT 원문 JSON 대신 저장 점수/상태와 비식별 설명 재생, 원본 possible-order 응답이 없어 기록 현금/가격으로 cash-only 가능 수량을 구성하고 조회 시각만 가상 현재로 갱신, 초기 계좌 조회의 60초 재시도 자체는 생략하고 기록된 정상 잔고부터 시작, 최초 정상/불확실 제출 이후는 FakeBroker의 명시적 가상 응답, 13:25 복구는 실제 230 데이터를 더 일찍 받았다는 조건부 실험입니다. test01의 기존 주문 13번은 제거하지 않았습니다.

추가 파일은 `app/tests/support/production_replay_oct28.py`, `app/tests/integration/test_pr140_production_replay_20261028.py`, 이 보고서입니다. 기존 사용자 변경 `.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py`는 보존했습니다. 커밋·푸시·PR 생성·원본 DB 정리는 하지 않았습니다.
