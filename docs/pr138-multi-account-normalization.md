# PR138 후속: 멀티계정 KIS 정상화와 가상 매수 검증

추가 필수 요구사항인 계정별 실제 리스크 엔진·게이트 판정·차단 매트릭스의 최신 검증은 [별도 보고서](pr138-account-risk-gate-verification.md)와 [전체 게이트 JSON](pr138-account-risk-gate-verification.json)에 기록한다.

주문 #14의 후속 실제 KIS 체결 대조·승인 대기 복구안·격리 테스트 결과는 [정합성 복구 보고서](pr138-order14-reconciliation.md)에 기록한다. 이후 조사에서 실제 전량 체결 SELL임을 확인했으며, 아래의 최초 원인 미확정과 운영 DB 비변경 기록은 당시 관측으로 보존한다.

기준: `pr138-market-regime-shadow`, `c21ae9c`. 검증일: 2026-10-21 KST.
이 문서는 합성 시세·GPT Mock·격리된 테스트 DB의 결과와 기존 DB 읽기 전용 관측을 구분한다.
운영 주문, 취소, DB 갱신, 서버 재시작, 설정 변경은 실행하지 않았다.

## 1. 결론과 운영 증거

관리자·test01·신규 test02가 같은 점수 기준과 실제 서비스의 Risk 검사를 거쳐 각각 Fake BUY 1회, 실제 주문 동기화 서비스의 FILLED 및 소유자별 포지션 저장까지 완료했다. 두 일반 사용자는 동시에 실행했다. 전체 원본은 [가상 사이클 JSON](pr138-multi-account-simulation.json)에 저장했다.

JSON에는 공통 200종목의 A 점수, 계정별 50종목의 A/C/GPT/Final 관측값과 계산 여부, 후보 계보, 단계 상태, 차단 사유 및 시간도 포함한다. GPT 미실행 후보의 Final 값을 실제 GPT 완료 결과로 취급하지 않도록 `final_calculated`를 함께 기록했다.

**운영 test01의 모든 차단을 잘못된 브로커 duplicate로 확정할 수 없다.** 기존 DB에는 test01 소유 로컬 SELL 미해결 행이 실제로 존재한다. 이 보호를 제거하거나 해당 행을 정리하지 않았다.

| 읽기 전용 관측 | 확인 내용 |
|---|---|
| 11:30 | 사용자 결과 HOLD, ledger HOLD, 보유 0, `duplicate_open_sell_order`, 프로필/A/C/GPT/Final 미진입 |
| 12:30 | `account_snapshot`, `UserBrokerUnavailableError`, 3회 소진, failed |
| 13:30 | 사용자 HOLD, ledger failed; 저장된 재시도 정보는 2회 후 복구 |
| 공통 Watchlist | 각 슬롯 이전 200/200 저장 확인 |
| 로컬 주문 #14 | owner=2, KIS/KR SELL, 종목 028670, 수량 5, 체결 수량 0, `UNKNOWN_STALE` |
| 해당 행의 생성·마지막 동기화 | 10/14 11:30 KST 생성, 10/19 17:12 KST 마지막 조회, `kis_order_not_found_in_inquiry` |
| 해당 행의 메타데이터 | provider=kis지만 request mode=`alpaca_live`; 생성 경위는 미확정 |
| 로컬 lifecycle | test01의 열린 lifecycle 없음; 관리자 기록은 closed |

확인된 로컬 차단 경로는 `UserAutoTradingSchedulerService._manage_positions()` → `position_management_block_reason()` → 같은 계좌의 활성/미해결 SELL 조회 → 주문 #14이다. 브로커가 빈 계좌를 반환하더라도 이 행 하나로 기존 코드가 `duplicate_open_sell_order`를 반환하는 조건이 충족된다. 새 테스트에서 같은 `UNKNOWN_STALE` + 빈 브로커 상태를 재현했고, 이제 `local_unresolved_sell_order`, 로컬 행 ID, 상태, 판정 소스를 남긴다. 다른 실계좌 사용자의 주문에는 영향을 주지 않는다.

위 슬롯의 읽기 전용 진단 출력은 [기존 기록 JSON](pr138-existing-slot-diagnostics.json)에 보존했다. 현재 로컬 미해결 주문 근거는 과거 브로커 원본 응답과 구분되어 있다.

당시 KIS 원본 응답, 이 행이 생성된 경위 및 조회에서 사라진 원인은 확보하지 못했다. **운영 장애의 최초 원인과 12:30 실패의 세부 원인은 `root_cause_unconfirmed`다.** 현재 빈 브로커 조회만으로 과거 주문을 취소/체결 완료로 간주하지 않는다. 보존된 미해결 주문 때문에 운영 test01은 이 변경 이후에도 안전하게 차단될 수 있다.

## 2. KIS 응답 대조와 수정 전·후

공식 TTTC0084R 예제는 정정·취소 가능 주문을 `output`으로 반환한다. `ord_qty`는 주문 수량, `tot_ccld_qty`는 총체결 수량, `psbl_qty`는 정정·취소 가능 수량이다. 공식 필드 목록에는 일반적인 `status`가 없다. `psbl_qty`를 단순히 주문 수량에서 빼서 체결량을 만들면 취소된 수량을 체결로 잘못 취급할 수 있다. [KIS 공식 필드 목록](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_psbl_rvsecncl/chk_inquire_psbl_rvsecncl.py), [KIS 공식 조회 구현](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_psbl_rvsecncl/inquire_psbl_rvsecncl.py).

공식 조회는 매도=01, 매수=02를 사용하는 기존 변환과 일치한다. INQR_DVSN_2=0은 양방향 전체이며, 조회 자체가 일반적인 주문 상태 검증을 대체하지 않는다. 연속 페이지가 있는 응답도 완전한 빈 계좌로 사용하지 않는다. 현재 변경은 연속조회 필요 시 `incomplete_snapshot`으로 차단하며 읽기 호출·타임아웃을 무조건 늘리지 않는다.

| 입력 | 이전 | 이후 |
|---|---|---|
| 보유 0, 주문 0, 신뢰 가능한 조회 | entry_scan | entry_scan 유지 |
| status 없음, SELL, ord=2/체결=2/가능=0 | pending으로 생성 → duplicate | filled → entry_scan |
| status 없음, 취소 확인, 가능=0 | pending으로 생성 → duplicate | canceled → entry_scan |
| 명시적인 잔여 0 | non-terminal status면 duplicate 가능 | inactive; 체결/취소를 임의 생성하지 않음 |
| psbl=0만 있고 체결/취소 근거 없음 | pending → 포괄 duplicate | `order_status_unverified` HOLD |
| 실제 활성 SELL, 양수 잔여 | 포괄 duplicate | `broker_active_sell_order` HOLD + 마스킹된 근거 |
| 주문 조회 불가/누락 | 포괄 예외 가능 | `open_orders_snapshot_unavailable` HOLD |
| 로컬 UNKNOWN_STALE SELL | 포괄 duplicate | `local_unresolved_sell_order` HOLD; 행 보존 |
| 같은 슬롯 재호출 | duplicate_scheduler_slot | 동일 보호 유지 |

11:30·13:30 재현 테스트는 과거 코드의 `status or pending` 및 수량을 보지 않는 SELL 판정을 그대로 대조식으로 검증한 후, 동일 Fake KIS 행이 수정된 경로에서 entry_scan으로 진행함을 확인한다. 이것은 **실재하는 정규화 결함의 재현**이며 그 행이 당시 운영 응답이었다는 증거는 아니다.

새 주문 판정은 진입 전과 주문 직전의 새 계좌 스냅샷에 모두 적용한다. 상태 불확실, 잘못된 수량, 미해결 로컬 주문을 허용하는 예외는 없다.

## 3. 중복 차단 경로 조사

아래는 `duplicate_open_sell_order` 사용 파일 전체를 판정/소비 경로별로 정리한 목록이다. 관리자 및 기존 매도 API 계약은 유지하고, 일반 사용자 진입 경로에서 구체적인 사유를 추가했다.

| 파일/경로 | 무엇과 무엇이 중복되는가 / 처리 |
|---|---|
| `user_auto_trading_scheduler_service.py` | 다음 진입과 계좌의 활성 SELL 또는 미해결 exit가 충돌. broker/local/lifecycle/retry를 구분 |
| `kis_order_account_scope.py` | 같은 실계좌의 미해결 로컬 SELL과 다음 진입. 소유자 및 실제 계좌 동일성을 검증; legacy 호출의 alias 유지 |
| `kis_snapshot_order_state.py` | 정규화된 브로커 활성 SELL과 새 진입; 불확실성은 별도 코드 |
| `user_trading_execution_service.py` | 사용자 exit와 같은 종목 SELL 중복; 진입의 마지막 새 스냅샷에서도 재검증 |
| `kis_automation_execution_core.py` | 제출 예정 주문과 브로커/로컬 기존 주문 충돌. 기존 `duplicate_check_source=broker/local_db` 유지 |
| `kis_position_lifecycle_service.py` | 현재 lifecycle exit와 기존 exit_order/미해결 SELL 충돌. closing과 열린/불명확 매도를 보호 |
| `kis_position_management_service.py` | 보유 종목과 같은 종목 SELL 충돌을 후보의 blocked_by에 반영 |
| `kis_limited_auto_sell_service.py` | 매도 후보와 동일 종목 미체결 SELL; 승인/실행 시 중복 flag 재확인 |
| `profile_aware_guarded_live_auto_exit_service.py` | 프로필 매도 후보와 기존 브로커/로컬 SELL 충돌; 미리보기와 제출 게이트에서 확인 |
| `auto_sell_live_phase1_service.py` | 선택 후보의 open_sell_order_conflict 및 기존 SELL을 제출 전 재검사 |
| `kis_live_exit_preflight_service.py` | 위 후보/로컬·브로커 충돌을 no_duplicate 체크와 blocked_by로 전달 |
| `operation_test4_service.py` | 계좌 open order 또는 로컬 SELL과 새 exit 충돌; review/disarm 유지 |
| `kis_exit_shadow_decision_service.py` | shadow exit 후보가 기존 SELL과 충돌함을 기록; 제출하지 않음 |
| `auto_exit_candidate_service.py`, `position_exit_review_service.py` | 상류 중복 flag를 후보/검토 결과에 전달; 독립적인 새 주문 권한 없음 |
| `kis_scheduler_guarded_sell_service.py`, `kis_scheduler_guarded_sell_review_service.py` | scheduler 매도 판정의 duplicate 체크 및 결과·사유 표시/정규화 |
| `kis_shadow_exit_review_queue_service.py` | 중복 사유의 검토 큐 분류; 주문 제출 없음 |
| `automation_scheduler_service.py` | 기존 매도 중복 결과를 retry job의 resolved_existing_order로 반영 |

closing lifecycle은 새 진입에 `position_exit_in_progress`, 로컬 미해결 SELL은 `local_unresolved_sell_order`로 구분된다. 주문 상태가 불명확한데 활성 매도가 확인됐다고 표현하지 않는다. 같은 슬롯 claim과 실제 주문 예약/제출 idempotency는 서로 다른 보호이며 모두 유지한다.

## 4. 계좌 조회·재시도·ledger

토큰, 잔고, 주문 조회를 `read_operation=token/balance/open_orders`로 구분한다. HTTP 429/500/502/503, Timeout, ConnectionError, JSON 오류, 응답 구조 오류, KIS msg_cd를 Fake HTTP로 검증했다. 로그는 owner_user_id, 환경, 시각, 시도 번호, 실제 소요시간, 최종 성공/실패와 허용된 코드만 저장한다. 원문 msg1, 요청 헤더, 토큰, 계좌 번호, 키/시크릿은 기록하지 않는다.

최대 3회, 재시도 간격 30초와 기존 제한을 유지한다. 토큰 서버의 일시적인 5xx/429/파싱 실패를 영구 인증 오류로 잘못 분류하지 않는다. 인증·설정 오류는 기존대로 자동 재시도 대상에서 제외한다.

기존 dispatcher는 retry_pending을 곧바로 failed로 기록했고 나중에 끝난 사용자 claim과 ledger가 동기화되지 않았다. 이제 ledger도 retry_pending으로 유지하며, 2회/3회 후 복구되면 HOLD/blocked/completed 등 실제 최종 결과를 저장한다. 3회 소진은 failed다. 이미 timeout으로 닫힌 ledger는 다시 열지 않는다. 미완료 재시도도 기존 300초 감시 만료 대상이다. 종료되거나 지난 슬롯을 재실행하지 않는다.

과거 12:30 로그에는 HTTP 상태·KIS 코드·조회 종류가 없다. 이번 Fake 재현의 성공/실패 내역을 과거 실제 오류의 원인으로 대신 기재하지 않는다.

## 5. 세 계정 전체 가상 사이클

다음 표는 합성 데이터의 통과 시나리오다. 당시 운영 성과를 나타내지 않는다. 관리자 가상 시각은 11:20, 두 일반 사용자는 11:30 KST이며 후자는 실제 두 worker에서 병행했다.

| 검증 단계 | 관리자 | test01 | test02 |
|---|---|---|---|
| Scheduler Slot | 관리자 dispatcher 완료 | 소유 claim 완료 | 신규 소유 claim 완료 |
| KIS Snapshot | Fake / 정상 | Fake HTTP 정규화 / 정상 | 독립 Fake HTTP / 정상 |
| Position Management | 빈 계좌 진입 | ENTRY_SCAN | ENTRY_SCAN |
| Watchlist 200 | 200 | 200 | 200 |
| Profile Watchlist 50 | 50 | 50 | 50 |
| A Top 5 | 5 | 5 | 5 |
| C65 Gate | 5 통과 | 5 통과 | 5 통과 |
| GPT Mock | 5 완료 | 5 완료 | 5 완료 |
| GPT60 Gate | 통과 | 통과 | 통과 |
| Final65 Gate | 통과, 1개 선택 | 통과, 1개 선택 | 통과, 1개 선택 |
| Risk Engine | 승인 | 승인 | 승인 |
| Fake BUY | 1 | 1 | 1 |
| Fake FILLED | 1 / lifecycle 저장 | 1 / 소유 lifecycle 저장 | 1 / 소유 lifecycle 저장 |
| Actual Broker Submit | 0 | 0 | 0 |

공통 시세만 공유한다. 암호화된 Fake 자격증명, 계좌 잔고 조회, 프로필, snapshot, A/C/GPT 감사, SignalLog, TradeRunLog, OrderLog, lifecycle, 거래 제한, 슬롯 claim은 소유자별로 검증했다. 동일한 종목을 선택해도 주문·포지션이 계정 사이에 섞이지 않는다. test01의 과거 완료 SELL은 entry_scan을 방해하지 않는다. 다른 계좌의 로컬 미해결 SELL 역시 test01의 진입을 막지 않는다. 같은 실계좌를 공유할 때의 기존 보호는 유지한다.

새 test02는 테스트 DB에서만 생성했다. 자격증명 저장 시 자동 실거래 동의가 해제되는 기존 동작을 확인한 후, **테스트 설정에 한해** 명시적으로 Fake 자동매매를 승인했다. 신규 사용자의 운영 기본 비활성 정책은 바꾸지 않았다.

| 계정 | 샘플 종목 | A | C | GPT Mock | Final |
|---|---|---:|---:|---:|---:|
| 관리자 | 000100 | 44.00 | 74.24 | 70.00 | 73.18 |
| test01 | 000100 | 44.00 | 81.67 | 70.00 | 78.75 |
| test02 | 000100 | 44.00 | 81.67 | 70.00 | 78.75 |

A는 후보 순위 계산에 쓰이며 진입 점수 65 기준은 C 및 Final에 그대로 적용된다. 일반 사용자 분봉은 11:30의 가상 시각까지 이동한 합성 시계열이다. 미래 시세를 사용하지 않는다.

테스트의 실제 transport 관측은 `simulation_only=true`, `real_order_submitted=false`, `actual_kis_submit_count=0`, `broker_submit_called=false`, `mock_submit_count=1`, `simulated_order_status=FILLED`다. 프로덕션 실행 서비스 내부의 live 제출 flag는 주입된 Fake client 호출에도 true가 될 수 있다. JSON의 transport 관측과 그 내부 flag를 혼동하지 않는다. 실제 KIS submit 메서드 및 HTTP/socket 연결은 금지 패치가 실행 즉시 테스트를 실패시키도록 구성했다.

## 6. 회귀·거절·시간 검증

- 관리자: 별도의 하락 합성 분봉으로 200 → 50 → A5 → C5 analyzed → C65 통과 0 → GPT 0 → 주문 0을 검증했다.
- test01/test02: GPT59 및 GPT Timeout 계정과 정상 계정을 동시에 실행해 정상 계정의 Fake FILLED를 확인했다.
- 실제 일일 거래 한도, 불확실한 계좌, 장 종료는 제출 전에 차단했다.
- GPT 응답이 매수 허용 시간 이후 도착하면 `scheduler_task_expired_before_buy`로 종료하며 Fake BUY도 0이다. 일반적인 제출 실패로 뭉개지 않고 정확한 만료 사유를 보존한다.
- 기존 replay에는 Final63.75 차단, Risk/kill switch, max positions, possible-order 10초, cash-only, 예약·중복·idempotency, TP/SL, 계좌 스코프, 만료 worker의 늦은 BUY 차단이 포함된다.

시간은 `perf_counter/monotonic`으로 측정한 로컬 처리시간이며 가상 시장 시각과 별개다. 실제 운영의 80~91초 분석 시간과 비교해 API 성능이 개선됐다고 주장하지 않는다. 단계 시간에는 중첩 구간이 있으므로 각 값을 합해 total로 해석하면 안 된다. 관리자 계좌/포지션/Risk 시간은 테스트 probe로 누적 관측했고 관리자 매매 순서는 바꾸지 않았다. 실제 측정값은 JSON 및 아래 표에 기록한다.

| ?? (ms) | ??? | test01 | test02 |
|---|---:|---:|---:|
| Account Snapshot | 0.025 | 10.194 | 1.270 |
| Position Management | 5.461 | 41.005 | 31.340 |
| Profile Watchlist | 48.637 | 349.400 | 383.383 |
| A Quant | 472.760 | 1007.780 | 1390.050 |
| C Quant | 150.330 | 164.860 | 169.500 |
| GPT | 117.340 | 812.730 | 233.780 |
| Final Ranking | 162.470 | 335.660 | 296.570 |
| Risk Engine | 40.341 | 17.012 | 5.795 |
| Total | 2959.163 | 4882.382 | 5096.676 |

## 7. 읽기 전용 진단

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_user_auto_trading.py --user test01 --date 2026-10-21
```

`--json`과 `--database <기존 SQLite 파일>`도 지원한다. SQLite `mode=ro` + `query_only`를 사용하고 누락된 DB를 만들지 않는다. 분석·주문·마이그레이션 서비스를 import하지 않는다. 테스트에서 DB 해시 불변, 쓰기 거절, 다른 사용자 격리, 미진입 점수와 실제 0점의 구별을 확인했다.

스크립트는 `NOT REACHED`, `NOT CALCULATED`, 실제 0점, 실패, HOLD를 구분한다. 공통 Watchlist의 저장 완료와 사용자 분석 진입도 구분한다. 과거 로그에 없는 정보는 UNKNOWN으로 표시하며 현재 미해결 로컬 주문은 사건 당시 브로커 스냅샷과 별도로 표시한다. DB의 과거 failed ledger나 상태를 조회 과정에서 교정하지 않는다.

새 실행의 `run_diagnostics`, position_management 및 pipeline diagnostics는 기존 TradeRunLog 응답에도 보존한다. Flutter는 변경하지 않았다. 기존 Logs/History의 JSON 진단 데이터를 사용할 수 있고 새 UI에 의존하지 않는다.

## 8. 변경 파일과 검증 결과

| 파일 | 변경 이유 |
|---|---|
| `app/services/user_broker_account_service.py` | KIS 수량 기반 상태·신뢰도, 조회 종류/코드/시간, 일시 토큰 실패 분류, 불완전 페이지 차단 |
| `app/services/kis_snapshot_order_state.py` | 진입 및 마지막 계좌 재조회에 같은 보수적 주문 판정 적용 |
| `app/services/kis_order_account_scope.py` | 기존 계좌 격리를 유지하며 로컬 주문/lifecycle/retry 근거 제공 |
| `app/services/user_auto_trading_scheduler_service.py` | 구체적인 HOLD 사유, 소유 스냅샷 전달, 재시도 이력, ledger 최종 결과, 단계 진단 |
| `app/services/automation_run_diagnostics.py` | 계정/worker context별 측정값 분리 |
| `app/services/account_snapshot_retry.py` | 민감 정보를 제외한 조회 실패 메타데이터 전달 |
| `app/services/scheduler_slot_dispatcher.py` | retry_pending 보존·만료 감시 및 최종 결과의 일관성 |
| `app/services/kis_watchlist_preview_service.py` | 사용자 분석에서 관리자 보유 계좌 조회 방지; 점수 계산 유지; 최종 순위 시간 |
| `app/services/user_trading_execution_service.py` | 새 스냅샷 주문 신뢰도 재검사, 만료 BUY 차단 사유, Risk 측정 |
| `scripts/diagnose_user_auto_trading.py` | DB 읽기 전용 슬롯 진단 CLI |
| 신규 테스트 4개 파일 | 전체 가상 사이클, duplicate 전후 재현, retry/ledger, 오류 분류·비밀정보 제외, 읽기 전용 보증 |
| `app/tests/no_external_transport.py` | 전체 Backend 실행에서 외부 TCP 연결 금지; 로컬 테스트/event loop 통신만 허용 |
| 기존 테스트 2개 파일 | 공식 `tot_ccld_qty` Fake 필드 및 새 명시적 불확실성 코드 검증 |
| 이 보고서·JSON | 재현 결과, 점수, 시간 및 미확정 운영 원인 보존 |

`.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py`는 사용자 변경으로 보존하며 커밋하지 않는다.

| ?? | ?? ?? |
|---|---|
| ?? scheduler replay | 39 passed |
| ?? full lifecycle replay | 19 passed |
| ?? ??? scheduler | 45 passed (? ? replay? ?? ?? ??: 103 passed) |
| ?? ?? ?? ??? | 70 passed |
| ?? 4? ??? ?? | 70 passed, ?? Backend? ?? |
| ??? HOLD/failed ledger ?? | ?? ?? 3 passed |
| ?? Backend | **2,566 passed, 0 failed, 0 error, 0 skipped**, 1,448.47? |
| ?? ?? | ?? ???? `app.tests.no_external_transport` ?? |
| python -m compileall app | exit 0 |
| git diff --check | exit 0 |
| Flutter | ?? ??, ?? ?? ?? |

?? ??? ?? 10?? ?? websockets/FastAPI deprecation ? OpenAPI operation ID ????. ?? ?? ??? ?? Backend ?? ?? ???? ???.

?? ??:

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests -q -p app.tests.no_external_transport --basetemp=.tmp/pr138_followup_verified_full -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest app/tests/integration/test_kis_automation_scheduler_replay.py app/tests/integration/test_kis_automation_full_lifecycle_replay.py app/tests/test_user_auto_trading_scheduler_pr129.py -q -p app.tests.no_external_transport --basetemp=.tmp/pr138_followup_final_replays -p no:cacheprovider
.\.venv\Scripts\python.exe -m compileall app
git diff --check
```


운영 반영 전에는 주문 #14의 생성·동기화 근거를 별도로 확인해야 한다. 이 변경은 해당 행을 자동으로 종료하거나 삭제하지 않는다. 당시 원본 응답/HTTP 코드가 없으므로 운영 장애의 최초 원인은 미확정이며 실계좌 API 연동과 실제 체결 성능은 이번 작업의 검증 대상이 아니다. 임계값·실거래 권한·kill switch·거래 횟수·타임아웃을 완화하지 않았다. 새 PR 생성과 main 병합은 수행하지 않는다.
