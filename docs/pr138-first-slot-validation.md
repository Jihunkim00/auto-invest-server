# PR138 추가 검증: 2026-10-20 첫 매수 분석 슬롯

## 결론과 운영 증거의 한계

첫 매수 **분석** 슬롯은 관리자 `11:20 KST`, test01 `11:30 KST`다. `07:37~09:17`의 Watchlist 갱신과 KIS 잔고 조회는 사전 준비·기존 포지션 감시이며 첫 매수 분석으로 세지 않는다. 분석 실행은 주문 제출과도 구분한다. 점수가 부족하면 분석과 TradeRunLog 저장이 성공해도 주문은 발생하지 않는다.

실제 사고의 원인은 **`root_cause_unconfirmed`**다. 운영 로그에는 `09:17:39` 잔고 조회 실패와 `09:18:39` 재시도 예약이 있고, `11:20`·`11:30`의 실행 여부를 설명할 traceback·당시 heartbeat·스레드 덤프가 없다. 마지막 로그가 `09:17`이라는 사실로 그때 스케줄러가 종료됐다고 판단하지 않았다. `09:02`의 같은 HTTP 500 이후 `09:04`에 `resolved_hold`로 처리된 기록도 있다. 이후 운영 DB의 분석·주문 0건은 사용자 제공 관측이며 운영 DB는 열지 않았다.

기준 커밋 `dd6269d`의 루프는 `_selected_profile_schedule()`·`due_slots()` 등에서 처리되지 않은 DB 예외로 종료될 수 있었고, 순차 보조 작업의 대기 때문에 슬롯 확인을 놓칠 수 있었다. 이전 PR138 수정은 planner·보조 작업·계정 worker를 분리하고 오류·누락을 기록한다. 이번 대조 실험에서 **수정된 코드의 09:17 HTTP 500만으로는 11:20·11:30 누락이 발생하지 않았다.** 별도로 첫 슬롯의 프로필 조회/사용자 슬롯 발견에 DB 오류를 주입하면 해당 슬롯이 누락되는 경로를 재현했다. 이는 가능한 실패 경로의 증명이며 당시 DB 오류 발생이나 KIS 오류와의 인과관계를 입증하지 않는다.

## 실행한 경로

`test_pr138_first_buy_slot_timeline.py`는 테스트 객체의 `start()`로 실제 scheduler thread와 `_run_loop()`를 실행한다. 가상 시계만 순서대로 전진시키고 각 시점의 worker가 끝난 뒤 검증한다. 시스템 시계, 운영 scheduler, 서버 프로세스는 조작하지 않는다.

실제 프로필 DB 조회, 관리자 `_profile_slots()`, 사용자 `due_slots()`와 프로필 시각 계산, 영속 `AutomationSchedulerSlot` claim, 사용자 `run_provider_once()` dispatcher, `UserAutoTradingSlotClaim`, 실제 분석·TradeRunLog 저장을 사용한다. 관리자·사용자는 별도 세션과 테스트 계정이다. 준비 작업만 Fake KIS 잔고 조회 probe로 대체해 실제 supervisor의 오류 격리를 검증한다. 기존 포지션 감시·재시도 상세 경로는 별도의 필수 replay 및 PR138 장애 replay가 검증한다.

heartbeat, 마지막 tick, 프로필 실행 완료 시각이 같은 주입 시계를 사용하도록 진단 시각을 맞췄다. 운영 기본값은 실제 시각이다. 테스트는 요청한 시각에 tick을 주입한다. 운영은 기존 20초 polling이므로 `HH:MM:00`에 정확히 깨어남을 보장하는 검증은 아니다. 해당 예약 분의 첫 tick에서 실행할 수 있고, 예약 분을 넘긴 BUY는 차단한다.

## 시간순 결과: 09:17 HTTP 500 단독 주입

각 행에서 관리자 프로필은 `11:20 / 12:20 / 13:40`, test01은 `11:30 / 12:30 / 13:30`으로 계산됐다. scheduler thread는 모든 시점에 활성 상태였고 heartbeat/tick은 해당 가상 시각과 일치했다. `TradeRunLog`와 claim 수는 누적값이다. 슬롯 원장 6건은 미리 등록되지만 예약 전에는 `pending`, `started_at=null`이다.

| 가상 KST | tick / health | 새 분석·claim | 사용자 due_slots / dispatcher 누적 | TradeRunLog 누적 | 시작된 슬롯 누적 |
|---|---|---|---|---:|---:|
| 09:17:00 | 실행 / degraded | 없음; Fake 잔고 조회 HTTP 500 | 없음 / 0 | 0 | 0 |
| 10:00:00 | 실행 / healthy | 없음; 잔고 조회 회복 | 없음 / 0 | 0 | 0 |
| 11:19:50 | 실행 / healthy | 없음; Watchlist 사전 준비 | 없음 / 0 | 0 | 0 |
| 11:20:00 | 실행 / healthy | 관리자 첫 분석 | 없음 / 0 | 1 | 1 |
| 11:29:50 | 실행 / healthy | 없음 | 없음 / 0 | 1 | 1 |
| 11:30:00 | 실행 / healthy | test01 첫 분석 | 11:30 / 1 | 2 | 2 |
| 12:20:00 | 실행 / healthy | 관리자 두 번째 분석 | 없음 / 1 | 3 | 3 |
| 12:30:00 | 실행 / healthy | test01 두 번째 분석 | 12:30 / 2 | 4 | 4 |
| 13:30:00 | 실행 / healthy | test01 세 번째 분석 | 13:30 / 3 | 5 | 5 |
| 13:40:00 | 실행 / healthy | 관리자 세 번째 분석 | 없음 / 3 | 6 | 6 |

시간순 검증에서는 Fake GPT를 59점으로 설정해 주문 없이 여섯 번의 분석을 확인했다. 최종 원장 상태는 관리자 세 슬롯 `blocked`, test01 세 슬롯 `HOLD`다. 사용자 claim은 해당 사용자·KIS·2026-10-20·예약 슬롯에만 생성됐다. 분석 시작 전 TradeRunLog는 0건이고 전체 주문은 0건이다. 오류를 넣지 않은 대조군도 같은 여섯 분석 결과이며 `09:17`부터 health가 `healthy`다.

## 첫 슬롯 발견 오류 대조군

09:17 Fake 잔고 HTTP 500에 더해, 관리자 `11:20`의 `_selected_profile_schedule()`와 test01 `11:30`의 `due_slots()`에 각각 합성 `OperationalError`를 넣었다. 해당 planner 오류는 traceback과 `degraded` health로 관측됐다. 해당 시점에는 claim/분석/TradeRunLog가 없었으며, 예약 분을 지난 두 슬롯은 `missed`로 영속 기록됐다. 이후 `12:20 / 12:30 / 13:30 / 13:40`의 네 분석은 실행됐다. 실제 루프는 계속 살아 있었고 지난 두 슬롯을 소급 주문하지 않았다.

이 대조군은 요청한 시점만 전진시키므로 같은 예약 분 안의 추가 tick에서 DB가 회복되는 상황을 검증하지 않는다. 오류가 예약 분의 유일한 관측 tick을 막았을 때의 결과다. 모든 시점별 프로필·due 계산·claim 상태·로그 결과는 [JSON 원본](pr138-first-slot-timeline.json)에 저장했다.

## 정상화된 11:20 전체 사이클

별도 테스트는 `09:17 HTTP 500 → 10:00 활성 → 11:19:50 준비 → 11:20 관리자 분석`을 같은 실제 루프로 실행했다. 시각 검증과 구분해 GPT를 70점으로 설정하고 기존 매수 안전장치를 그대로 통과시켰다. 역사적 10월 20일 시장 데이터가 아닌 **합성 fixture 복원**, **GPT MOCKED**다.

| 단계 | 실행한 서비스 / 입력 | 결과 |
|---|---|---|
| Watchlist | 실제 KR 로더·스냅샷, Fake OHLCV | 200종목 계산·저장 |
| A 및 Top 5 | 실제 A 계산·필터·순위 | 프로필 50종목 재계산·저장, Top 5 |
| C | 실제 15/30/60분 C 계산, 합성 분봉 | 5종목 analyzed |
| GPT | 실제 prompt·응답 파서, Fake Responses | 5종목, GPT MOCKED |
| Final | 기존 계산식 | 000100, C 74.24 / GPT 70 / Final 73.18 |
| Risk·주문 검증 | 실제 Risk·현금/한도/중복/possible-order/실행 권한 검사, Fake 계좌 | 주문 직전 승인 1건 |
| Fake Broker BUY | FakeBroker | 1회, 9주 |
| 주문 동기화·Lifecycle | 실제 동기화 서비스, Fake 체결 조회 | FILLED, open lifecycle 1건 |

결과는 `simulation_only=true`, `real_order_submitted=false`, `actual_kis_submit_count=0`, `mock_submit_count=1`, `simulated_order_status=FILLED`다. 첫 슬롯 전에는 주문·매수 분석이 없다. 임시 DB에만 후보·분석·주문·포지션을 저장한다. 테스트 fixture가 실제 KIS submit과 외부 HTTP를 금지한다. C65/GPT60/Final65, possible-order 10초, cash-only, max positions, 중복·예약·멱등성, daily cap, session/cutoff, TP/SL, 실행 권한을 완화하지 않았다.

장 마감 실시간 차단, GPT 점수 미달·timeout, 기존 장애 A/B/C 결과는 [통합 보고서](pr138-scheduler-incident-replay.md)를 함께 참조한다. 이번 추가 테스트 4건과 기존 필수·PR138 replay 71건, 전체 Backend 2,496건, Flutter 773건이 통과했다. Flutter analyze, `python -m compileall -q app`, `git diff --check`도 통과했다.
