# PR140 작업 보고

작업 브랜치: `pr140`. 커밋·푸시·PR 생성 없이 작업 트리에 반영했습니다.

1. **직접 원인과 확인 범위**: 기존 dispatcher는 슬롯 시각 +60초까지만 매수를 허용했고 계정 작업도 300초에 만료했습니다. 11:20 슬롯의 11:22:58 분석 완료는 이미 매수 기한 밖입니다. 주문·예약 저장 후 실행 코어 진입부의 `SchedulerTaskExpired`가 처리되지 않아 `REQUESTED`/`reserved`로 남을 수 있는 경로를 가상 시계와 FakeBroker로 재현했습니다. 주문 18번의 실제 브로커 접수 여부는 로컬 기록만으로 확정할 수 없습니다.
2. **매수 허용 시간**: `ACCOUNT_SLOT_BUY_WINDOW_SECONDS = 600`. 절대 마감은 원래 슬롯 시각에 고정합니다. 작업이 늦게 시작돼도 기한이 늘어나지 않습니다. 신규 슬롯의 시작 유효 기간 1분과 장 종료 후 재생 금지는 유지합니다.
3. **작업 제한**: `ACCOUNT_SLOT_TASK_TIMEOUT_SECONDS = 720`. 계정 dispatcher, supervisor, 슬롯 reconcile 및 expire_overdue가 같은 제한을 사용합니다. supervisor의 다른 유지보수 작업 제한은 유지합니다. 만료된 스레드는 실제 종료될 때까지 같은 계정의 실행 lane을 점유하며, 상태 조회 없이도 제출 검사에서 만료가 적용됩니다.
4. **REQUESTED 정리**: 새 주문의 검증 실패·검증 예외·작업 만료·제출 직전 안전 차단은 `REJECTED_BY_SAFETY_GATE`, 예약 `blocked`, 실제 차단 원인과 `broker_submit_called=false`, `real_order_submitted=false`를 기록합니다. 실패 실행 로그도 저장합니다.
5. **불확실한 제출 구분**: 브로커 호출 경계 직전에 `UNKNOWN_STALE` 및 복구 정보를 DB에 먼저 저장합니다. 요청 후 timeout, 응답 누락, 주문번호 누락은 `UNKNOWN_STALE`/예약 `sync_required`를 유지합니다. 이 기록은 프로세스 종료가 호출 경계에서 발생한 경우에도 보수적으로 해석합니다. 재호출·다음 슬롯에서 자동 재주문하지 않습니다. 영속 상태 저장 직후에도 기한·시장·권한·kill switch·주문가능금액 신선도를 다시 검사합니다.
6. **실제 거래와 미해결 위험**: KIS/KR에 한해 실제 `FILLED` 또는 양의 체결 수량이 기록된 주문을 하루 한 번 집계합니다. 부분 체결 후 취소도 실제 진입 한 건을 유지합니다. 가상 체결은 제외합니다. 미해결 주문은 별도 `unresolved_entry_count`로 진입 여유를 점유하며 이전 날짜의 미해결 주문도 유지합니다. 연결 주문이 누락된 성공/미확인 실행 로그는 실제 체결 근거로 사용하지 않고, 중복 제거한 미해결 위험으로 보존합니다. 기존 일일 최대 횟수와 계정·프로필 범위는 유지합니다. Alpaca 집계는 변경하지 않습니다.
7. **주문 18번**: `python app/scripts/inspect_kis_unsubmitted_order.py --db auto_invest.db --order-id 18`로 읽기 전용 확인했습니다. `REQUESTED`, 예약 10번 `reserved`, 주문번호·제출 시각·체결 수량 모두 NULL이며, 호출 여부 증거도 없습니다. DB를 변경하지 않았습니다. 브로커 주문·체결 대조 및 수동 승인 전에는 이 기록을 해제할 수 없습니다. 새 검사 스크립트는 조회 기능만 제공합니다.
8. **변경 파일**:
   - `app/services/scheduler_slot_dispatcher.py`
   - `app/services/scheduler_task_supervisor.py`
   - `app/services/automation_profile_buy_scheduler_service.py`
   - `app/services/kis_automation_execution_core.py`
   - `app/services/kis_daily_entry_accounting.py`
   - `app/services/strategy_risk_budget_service.py`
   - `app/services/account_trading_limit_service.py`
   - `app/services/automation_scheduler_service.py`
   - `app/services/automation_today_decision_service.py`
   - `app/scripts/inspect_kis_unsubmitted_order.py`
   - `app/tests/conftest.py`
   - `app/tests/integration/test_pr140_buy_timeout_lifecycle.py`
   - `app/tests/test_pr140_order_status_feed.py`
   - `app/tests/integration/test_kis_automation_pr117_live_position_management.py`
   - `app/tests/test_target_aware_risk_service.py`
   - `app/tests/test_kis_read_only_endpoints.py`
   - `lib/models/automation_today_decisions.dart`
   - `lib/features/dashboard/widgets/home_latest_ai_decision_card.dart`
   - `test/home_latest_ai_decision_card_test.dart`
   - 이 보고서
9. **신규 회귀 테스트**: 신규 파일의 PR140 백엔드 37개 통과(기존 실행 코어 테스트와 함께 45개 통과). 기존 일일 한도 테스트도 미해결 주문과 실제 체결 두 경우로 확장했습니다. 11:23 매수 허용, 11:30/11:31 차단, 12분 만료, 검증 예외, 다음 슬롯 복구, 불확실한 제출과 재실행 금지, 제출 경계 저장 직후 만료 및 브로커 미설정의 미제출 확정, 실제 체결/부분 체결/미해결 집계, 가상 체결 제외, orphan 로그 중복 제거, 시장·진입 마감·kill switch·권한·워치리스트 차단, 관리자/test01 상태 격리, 읽기 전용 검사, 작업 lane 보존을 포함합니다. Flutter에는 AI 승인과 미제출/제출/체결 상태 및 차단된 슬롯의 미제출 표시를 구분하는 4개 테스트를 추가했습니다.
10. **백엔드 검증**: 전체 **2,735개 통과**, 실패 0, 602.53초. 필수 `test_kis_automation_scheduler_replay.py`와 `test_kis_automation_full_lifecycle_replay.py` 합계 58개도 통과했습니다. `python -m compileall app`, `git diff --check` 통과. 전체 실행 명령은 `python -m pytest app/tests -q -p no:cacheprovider -n 8 --dist worksteal --maxfail=1`입니다. 격리된 8개 프로세스를 사용했으며, 전체 검증에는 작업 폴더 `.tmp/pr140-test-tools`에만 설치한 pytest-xdist/execnet을 사용했습니다(`PYTHONPATH`에 해당 경로 설정). 프로젝트 의존성 파일은 변경하지 않았습니다.
11. **Flutter 검증**: `flutter --no-version-check analyze` 통과(No issues found). `flutter --no-version-check test` 전체 783개 통과. AI 판단과 주문 상태가 각각 표시되므로 기존 HOLD 화면 테스트도 두 표시를 명시적으로 확인하도록 갱신했습니다.
12. **실제 KIS 제출 차단 증거**: PR140 테스트는 격리 DB와 FakeBroker/FakeKisClient를 사용합니다. 외부 requests/httpx 전송 및 실제 KisClient 제출 함수를 실패 처리합니다. 전체 backend 공통 fixture도 실제 KIS requests/httpx transport 접근을 차단합니다. 이 가드가 기존 가격 정규화 테스트의 누락된 잔고/봉 조회 mock을 발견하여, 해당 조회를 fake로 대체했습니다. 전송은 네트워크 호출 전에 차단됐으며 프로덕션 KIS 제출·계좌 조회는 수행하지 않았습니다.
13. **변경하지 않은 로직**: A/C Quant, EMA/RSI/VWAP/ATR, GPT 모델·프롬프트·점수, Final Score, C65/GPT60/Final65, 후보 순위, 사이징·복리 계산식, TP/SL, 손실·노출·최대 포지션·현금 전용 제한, 시장 마감 정책, KIS 인증·주문 payload, Alpaca paper trading, 계좌 재시도 60초·240초 정책은 유지합니다. 리스크 서비스 변경은 거래 집계와 미해결 주문의 한도 점유 분리에 한정합니다.
14. **남은 확인 사항**: 주문 18번의 실제 접수·체결 여부는 브로커 증거가 필요합니다. 13:30/13:45 워치리스트 snapshot 229 실패는 별도 이슈이며 이번에 점수·완전성 검사를 완화하지 않았습니다. 프로세스가 실제 제출 경계에서 종료되면 불확실한 주문은 계속 차단되며 수동 또는 기존 브로커 동기화가 필요합니다. 실제 계좌 주문으로 검증하지 않았습니다. 전체 pytest에는 deprecated API 및 중복 OpenAPI operation ID 관련 경고 59개가 남아 있습니다.

기존 사용자 변경인 `.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py`는 보존했습니다.
