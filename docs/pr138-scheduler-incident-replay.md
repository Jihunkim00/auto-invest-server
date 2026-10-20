# PR138: 2026-10-20 스케줄러 장애 수정 및 전체 사이클 검증

브랜치: `pr138-market-regime-shadow`. 기준 커밋: `dd6269d13ba8b62973c72893cc96bc0245ef7ad0`.

## 사고 원인: root_cause_unconfirmed

`logs/auto-invest-server.log`에서 다음 운영 기록을 직접 확인했다.

| KST | 확인한 기록 |
|---|---|
| 07:37:29 | AutomationSchedulerService 시작, thread alive |
| 07:44:12 | 200종목 스냅샷, 199종목 계산, 오류 1건, 402.641초 |
| 08:53:36 | 200종목 스냅샷 성공, 201.844초 |
| 09:02:16 | 포지션 조회 HTTP 500, 재시도 예약 |
| 09:03:17 | 재시도 실패, 다음 재시도 예약 |
| 09:04:19 | 재시도 `resolved_hold`, 제출 없음 |
| 09:17:39 | 포지션 조회 HTTP 500, 09:18:39 재시도 예약 |
| 16:23:39 | 서버 재시작 기록 |

해당 공백 구간에는 사고를 설명하는 traceback이나 스레드 덤프가 없다. KIS 500이 단독 원인인지, SQLite 경합인지, 스레드 종료인지, 특정 호출의 대기인지는 확정하지 못했다. 재시작 후의 정상 등록 상태도 오전 정상 실행의 증거로 사용하지 않았다. 운영 DB의 분석·주문 기록 0건은 사용자 제공 관측이며, 이번 작업에서 운영 DB를 열거나 수정하지 않았다.

관리자 첫 매수 분석은 **11:20**, test01 첫 매수 분석은 **11:30 KST**다. 07:37~09:17의 Watchlist·KIS 조회는 사전 준비와 포지션 감시이며 매수 분석 슬롯이 아니다. 09:17 이후 로그가 없다는 이유로 해당 시각의 스케줄러 종료를 단정하지 않는다.

기준 코드에서는 `_next_automation_run_at`, `_selected_profile_schedule`, `_dispatch_due_position_exit_retries`, 사용자 `due_slots`의 예외가 최상위 루프를 종료할 수 있었다. 주문 동기화, 포지션 감시, 관리자 분석, canonical Watchlist 유지 작업을 순차 실행해 다음 계정의 슬롯 확인을 지연시킬 수도 있었다. 마지막 tick은 전체 순차 작업 이후에만 갱신됐다. 이 경로들은 코드상 확인된 결함이며, 이번 사고의 직접 원인으로 확정한 것은 아니다.

운영 로그의 200종목 **공유 스냅샷** 갱신은 기존에도 `WatchlistSnapshotScheduler`의 별도 스레드였다. 따라서 402초/202초 지연 자체가 canonical 루프를 직접 정지시켰다고 단정하지 않는다. canonical 프로필용 Watchlist 유지 작업과는 구분해야 한다.

## 변경 내용

| 파일 | 변경 이유 |
|---|---|
| `app/services/automation_scheduler_service.py` | 20초 dispatcher, 관리자·사용자 planner 분리, 계정별 실행, 보조 작업 분리, 최상위 traceback, 진행 상태 기반 health, 세션에 묶인 서비스 캐시 제거 |
| `app/services/scheduler_task_supervisor.py` | 최대 32개 실행 작업, lane당 단일 실행, 대기 큐 없음, timeout 후 교체 금지, 취소 checkpoint와 BUY 차단 |
| `app/services/scheduler_slot_dispatcher.py`, `app/db/models.py` | 영속 슬롯 원장, atomic claim, terminal 상태, 지연·전일 슬롯 missed 처리, 재시작 중복·소급 실행 차단 |
| `app/services/user_auto_trading_scheduler_service.py` | 사용자 ID로 실행 범위 제한, 각 사용자 서비스의 분석 상태 격리, Watchlist 준비 상태 확인 |
| `app/services/kis_automation_execution_core.py`, `app/services/user_trading_execution_service.py`, `app/brokers/kis_broker.py`, `app/brokers/kis_client.py` | 제출 직전 취소·신선도 재확인, KIS read 전후 취소 checkpoint, 지연 응답 뒤 신규 BUY 차단 |
| `app/services/account_snapshot_retry.py` | 지연 재시도에도 원래 실행의 취소 context 전달 |
| `app/services/watchlist_snapshot_service.py`, `app/services/kis_watchlist_preview_service.py` | 종목 작업 사이 취소 checkpoint, GPT HTTP timeout 30초 및 SDK 자동 재시도 0회 |
| `app/routes/scheduler.py`, `app/services/runtime_diagnostics.py` | DB 조회 실패에도 읽을 수 있는 `/scheduler/health`, health/stage 시작 로그, 비정상 상태 경고 |
| `lib/models/scheduler_status.dart`, `lib/features/dashboard/dashboard_screen.dart` | heartbeat가 최근이어도 stalled/degraded/stopped면 정상 표시 차단 |
| `app/tests/integration/test_pr138_scheduler_failure_replay.py` | 장애 A/B/C, 실제 루프 예외·종료와 API 응답, 중복·지연·전일 슬롯 검증 |
| `app/tests/integration/test_pr138_full_pipeline_replay.py` | 실제 A/C/GPT 경로·Final·Risk·검증·Fake BUY·체결 동기화, GPT 점수 미달·timeout, 실제 장 마감 차단 |
| `test/scheduler_health_status_test.dart` | 최근 heartbeat만으로 정상 판정하지 않는 Flutter 회귀 검증 |

각 worker는 자체 DB 세션을 열고 닫으며 ORM 객체를 다른 worker에 전달하지 않는다. 일반 사용자 분석 서비스도 계정마다 새로 구성한다. timeout이 난 worker는 끝날 때까지 lane을 점유하므로 새 worker나 Future가 누적되지 않는다. KIS read의 기존 HTTP timeout 10초를 유지하고, read 전후·종목 사이에서 취소를 확인해 다음 작업을 중단한다. 이미 제출된 주문의 응답은 취소 때문에 버리지 않는다. SELL/TP/SL 제출에 BUY 슬롯 만료 조건을 적용하지 않는다.

슬롯은 당일 전체를 미리 등록한다. 시작하지 못한 슬롯은 예약 분이 지나면 `missed`가 되고, 시작한 작업이 300초를 넘으면 `failed`로 기록한다. 계정 worker가 점유 중이면 다음 슬롯은 `blocked`가 된다. terminal 기록은 다시 실행하지 않는다. BUY는 예약 분이 지난 뒤 제출하지 않도록 별도 deadline을 둔다. 공유 스냅샷은 당일 완료·성공·오류 0건·전체 점수 계산 완료·2시간 이내 조건을 확인한다.

`scheduler_engine_running`, `scheduler_heartbeat_age_seconds`, `scheduler_last_tick_at`, `scheduler_last_error`, `scheduler_health_status`, `scheduler_current_stage`, `scheduler_stage_started_at`, `scheduler_stage_duration_ms`, `scheduler_last_successful_slot`, `scheduler_last_failed_slot`, `scheduler_missed_slot_count`와 최근 슬롯 목록을 제공한다. 건강 판정은 dispatcher 생존, planner 진행, timeout 상태를 함께 확인한다.

## 장애 재현 결과

가상 날짜는 2026-10-20이며 시스템 시계를 변경하지 않았다. 아래 여섯 슬롯은 장애 주입용 Fake 계정 처리 결과다. 전체 주문 파이프라인 검증은 다음 절의 별도 테스트에서 수행했다.

| 계정 | KST | 결과 | 이유 |
|---|---|---|---|
| 관리자 | 11:20 | blocked | account_snapshot_unavailable |
| test01 | 11:30 | HOLD | no_candidate |
| 관리자 | 12:20 | blocked | account_snapshot_unavailable |
| test01 | 12:30 | HOLD | no_candidate |
| test01 | 13:30 | HOLD | no_candidate |
| 관리자 | 13:40 | blocked | account_snapshot_unavailable |

- A: 07:37 등록, 09:02 실패, 09:04 회복, 09:17 재실패와 장시간 포지션 감시 대기에도 여섯 슬롯을 모두 기록했다. 계좌 불명확 시 BUY는 차단됐다.
- B: 403초/202초 지연을 가상 시계와 대기 이벤트로 재현했다. 200종목 중 오류 1건인 스냅샷에서는 `watchlist_snapshot_not_ready`를 기록하고 BUY에 도달하지 않았다.
- C: DB/`due_slots` 예외의 traceback, heartbeat와 실제 tick의 분리, 실제 scheduler thread 종료 후 FastAPI `/scheduler/health`의 `stopped` 응답을 확인했다. 16:23 복구 시 여섯 과거 슬롯 모두 `missed`가 되고 실행 callback은 호출되지 않았다.
- 같은 슬롯의 다른 dispatcher 재등록은 중복 실행하지 않았다. timeout worker가 남아 있으면 교체하지 않으며, 늦게 반환된 작업의 추가 read와 BUY도 차단했다. 전일 pending 슬롯 역시 다음 날 `missed`로 닫았다.

추가 검증은 실제 테스트 scheduler thread로 `09:17 → 10:00 → 11:19:50 → 11:20 → 11:29:50 → 11:30 → 12:20 → 12:30 → 13:30 → 13:40`을 재현했다. 각 시점에 실제 프로필 계산, 영속 claim, 사용자 dispatcher, TradeRunLog를 확인했다. 09:17 Fake HTTP 500 단독 주입에도 여섯 분석이 실행됐다. 첫 두 슬롯에 별도의 프로필/`due_slots` DB 오류를 주입한 대조군에서는 두 슬롯만 `missed`, 이후 네 슬롯은 실행됐다. 이는 수정된 코드의 실패 격리 검증이며 실제 사고의 인과관계를 확정하지 않는다. 상세 시점표·전체 사이클과 30개 checkpoint 원본은 [첫 슬롯 추가 보고서](pr138-first-slot-validation.md)와 [JSON](pr138-first-slot-timeline.json)에 기록했다.

## 전체 자동매매 사이클

**역사적 시장 데이터를 사용한 재현이 아니다.** 저장소의 KR 200종목 universe를 읽고, 날짜를 맞춘 합성 일봉·분봉을 FakeKisClient로 공급한 fixture 기반 복원 테스트다. 점수를 직접 주입하지 않고 기존 지표·A·C 계산과 기존 점수 결합 공식을 실행했다. GPT는 `GPT MOCKED`이며 실제 GPT/API 호출은 하지 않았다. 시장·공시·계좌 입력도 Fake/미제공 상태를 명시한 테스트 입력이다.

| 단계 | 실행 여부 | 실제 계산 / Mock | 결과 |
|---|---|---|---|
| Watchlist 로드 | 실행 | 실제 로더·임시 DB, Fake OHLCV | 200종목 로드·검증·저장 |
| A 점수 계산 | 실행 | 실제 지표·A 서비스 | 스냅샷 200종목 계산, 프로필 50종목 재계산 |
| A Top 5 | 실행 | 실제 순위·필터 | 5종목 |
| C 분석 | 실행 | 실제 C 서비스, 합성 분봉 | 5종목 analyzed, 15/30/60분 계산, C65 통과 |
| GPT 판단 | 실행 | 실제 prompt·응답 파서, Fake Responses | GPT MOCKED, 5종목 처리 |
| Final Score | 실행 | 기존 결합 공식 | 000100 / C 74.24 / GPT 70 / Final 73.18 |
| Risk Engine | 실행 | 실제 위험·계좌 한도·possible-order·검증 로직, Fake 계좌 | 주문 직전 승인, 현금·한도·중복·실행 권한 유지 |
| Fake Broker BUY | 실행 | FakeBroker | 9주, 제출 1회, FAKE 주문번호 |
| Fake 주문 동기화 | 실행 | 실제 KisOrderSyncService·Lifecycle, Fake 체결 조회 | FILLED, open lifecycle 1건 |
| 장 마감 실시간 차단 | 실행 | 실제 시스템 시각·세션 판정, Fake 계좌 | market_session_closed / BLOCKED, Fake 제출 0회 |

가상 장중 결과: `simulation_only=true`, `real_order_submitted=false`, `actual_kis_submit_count=0`, `mock_submit_count=1`, `simulated_order_status=FILLED`. 가상 주문 수량은 9주이며, 주문·후보·포지션은 테스트 전용 DB에만 저장됐다. 실제 KIS HTTP 및 실제 GPT HTTP는 테스트 fixture에서 금지했다.

GPT 59점인 별도 테스트와 Fake GPT timeout 테스트는 정상 HOLD/차단으로 종료했고, 주문 검증·제출에 도달하지 않았다. 장 마감 검증은 가상 장중 시계와 별개로 실제 2026-10-20 KST 장외 시각을 사용했다.

## 회귀 검증

첫 슬롯 추가 검증을 포함해 전체 Backend와 필수 replay를 다시 실행했다. 아래 검증은 모두 통과했다.

| 검증 | 결과 |
|---|---|
| 필수 scheduler + full lifecycle replay | 58 passed |
| 기존 PR138 장애·전체 파이프라인 | 13 passed |
| 첫 매수 슬롯 시간순 추가 검증 | 4 passed |
| 전체 Backend pytest | 2,496 passed, 10 warnings, 1494.58초 |
| Flutter analyze | No issues found |
| Flutter test | 773 passed |
| python -m compileall -q app | 통과 |
| git diff --check | 통과 |

별도 replay 실행은 필수 58건과 기존 PR138 13건을 합해 71 passed였고, 시간순 추가 4건도 별도 실행 및 전체 Backend 실행에서 모두 통과했다. 총 replay는 75건이다. Backend 경고 10건은 websockets/FastAPI deprecation 및 기존 OpenAPI operation ID 중복 경고다.

C65/GPT60/Final65, possible-order 10초, cash-only, max positions, 동일 실계좌 중복·예약·멱등성, daily cap, market session/cutoff, TP/SL, 실행 권한, 시장국면 shadow 정책을 완화하지 않았다. 운영 DB 쓰기·실주문·실서버 재시작·운영 설정 변경은 수행하지 않았다. 기존 사용자 변경 `.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py`는 커밋 대상에서 제외한다.

## 남아 있는 운영 위험

실제 사고 원인은 여전히 미확정이며 운영 배포·재시작을 수행하지 않아 배포 후 정상 슬롯 실행은 확인하지 않았다. 실제 GPT 및 실제 KIS 지연·체결 품질도 합성 데이터 검증으로 입증할 수 없다. 영구적으로 반환하지 않는 외부 호출/DB 드라이버는 Python 스레드에서 강제 종료하지 않으며 해당 lane을 점유하고 health를 비정상으로 표시한다. 대체 worker와 후속 BUY는 차단된다. 특히 실제 분석이 예약 분 안에 끝나지 않으면 BUY deadline으로 차단하므로 운영 처리시간을 관찰해야 한다. 다음 운영 시작 시 신규 슬롯 테이블은 기존 `init_db()`의 `Base.metadata.create_all()` 경로에서 생성된다.
