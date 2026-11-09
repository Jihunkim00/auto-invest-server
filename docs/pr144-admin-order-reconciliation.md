# PR144 — 관리자 미완료 매수 주문 및 스케줄러 종료 정합성

## 운영 진단 결과

2026-11-09 운영 SQLite를 `mode=ro`와 `PRAGMA query_only=ON`으로 열었다. 인증 토큰 갱신 저장소는 메모리 DB로 분리했다. KIS에는 조회 GET과 필요한 인증만 수행했다. 실제 매수·매도·취소, #18 재제출, 원본 DB 정합성 복구는 수행하지 않았다. #13과 #19를 변경하지 않았다.

진단 수치와 복제본 실험은 [pr144-readonly-evidence.json](pr144-readonly-evidence.json)에 있다. 계좌번호, 앱 키, 토큰, 암호화된 인증정보는 포함하지 않는다.

| 슬롯(KST) | 실제 결과와 원인 |
|---|---|
| 11:10 | 11:11:35 분석 #329 종료. C 정량 게이트에서 실행 후보가 없어 `no_gpt_completed_execution_candidate`. 진입 한도까지 도달한 분석이 아니다. |
| 12:20 | 12:22:14 분석 #332와 슬롯 #93 모두 `unresolved_entry_limit_hit`. 당일 체결 0 + 과거 미완료 매수 1 >= 일일 한도 1. |
| 13:30 | 최초 계좌 조회 실패 후 60초 지연 재시도. 13:33:12 분석 #336은 `gpt_buy_score_below_threshold`로 종료했으나 부모 슬롯 #94는 `retry_pending`으로 남았다. 13:42:02.952에 만료 처리되어 `scheduler_task_timeout`으로 기록됐다. |

### 계좌 및 제한 계산

- 주문과 lifecycle의 관리자 legacy 소유자는 **NULL**이다. 관리자 사용자 ID **1**은 계좌 정책과 프로필 소유자다. `AccountTradingLimitService.resolve_account()`는 두 표현을 `admin:kis:KR`로 연결한다. `daily_entry_counts(owner_user_id=1)`로 대체하면 #18을 놓치므로 그렇게 변경하지 않았다.
- 11:10 / 12:20 / 13:30 기준 `daily_entry_counts()`는 모두 `(filled=0, unresolved=1)`이다. 진단용으로만 #18을 제외하면 `(0, 0)`이다. 날짜가 오래됐다는 이유로 unresolved를 제외하지 않았다.
- 활성 프로필 #5의 `entry.max_new_entries_per_day=1`, `max_trades_per_day=1`, `max_positions=1`이다.
- `StrategyRiskBudgetService`가 위 unresolved를 `max_trades_per_day`와 비교한다. 분석 #332의 `target_risk_result.profile_thresholds`에도 1이 기록돼 있다. 이것이 12:20의 직접 차단 지점이다.
- `AutomationProfileBuySchedulerService`도 동일한 accounting을 사용하고, `KisAutomationExecutionCore`는 제출 직전에 현재 주문만 제외해 다시 확인한다. 다른 미확정 주문은 계속 포함한다.
- `AccountTradingLimitService`는 NULL 관리자 주문을 대상으로 미완료 매수의 금액 노출도 별도로 예약한다. #18의 `notional=258,300원`이다. 관리자 금액 정책의 총액·종목 한도는 모두 NULL이므로 이번 직접 차단은 금액 한도가 아니다.
- #18에 연결된 예약 #10은 `reserved`, 주문 #18, 프로필 `aut_kis_eec5f898`, 10/28 11:20 슬롯이다. 예약 키는 보존한다. 계좌 execution claim 잔존은 0건, 활성 lifecycle도 0건이다.

## #18 제출 대사 및 판단

| 증거 | 확인 내용 |
|---|---|
| 주문 생성 | 10/28 11:23:00 KST, REQUESTED, 수량 7, 잔량 7. 브로커 번호·제출 시각·체결 수량·응답 없음. |
| 사전 분석 | 분석 #261은 11:22:58에 `LIVE_READY / target_aware_risk_approved`. 분석 요청의 submit=false는 분석 단계의 기록이며 이후 제출 부재를 증명하지 않는다. |
| 검증 | 검증 #15, 11:23:02, `validated_for_submission=true`. 이는 주문 제출 성공 또는 미제출 증거가 아니다. |
| 오류 로그 | 11:23:02.070에 같은 관리자 프로필, 11:20 슬롯, attempt=2의 `SchedulerTaskExpired`. 개별 주문 #18의 브로커 호출 경계를 확정하는 추적은 없다. |
| KIS 과거 주문 | 공식 전체 주문 필터 `CCLD_DVSN=00`, 10/28 당일 전체 페이지 조회 완료. 주문 0, 해당 종목 0, 미체결 0. |
| 현재 계좌 | 전체 당일 주문으로 확인한 현재 미체결 0, 보유 0. |
| 양성 미제출 증거 | 해당 주문 fingerprint에 연결된 완전한 제출 전 중단 journal은 없음. 실제 submit 호출 부재를 확정하지 못함. |

**판단: 운영 #18의 안전 종결 승인안 생성 거부 — `positive_pre_submit_evidence_missing`.** 빈 이력·빈 잔고와 KIS 번호 부재는 보조 증거다. 부분 제출·전송 이후 예외·결과 미확정 가능성을 단순히 배제하지 않는다. 운영 unresolved는 여전히 1이며 이 PR이 자동으로 매수를 허용하지 않는다.

KIS 필터와 TR ID는 [현재 공식 샘플](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py)을 기준으로 했다. 최근 실전 `TTTC0081R`, 과거 `CTSC9215R`; 체결 내역 홈 화면의 기본 `01`은 그대로 두고 대사 조회만 `00`을 요청한다. 연속조회는 응답 F/M, 다음 요청 N 및 FK/NK를 검증한다.

## 구현

### 승인 기반 안전 종결

- `KisOrderSubmissionEvidence`는 분석 로그와 분리된 제출 전 중단 journal이다. 신규 주문 생성 시에만 `durable_unknown_before_submit_v1` 프로토콜을 표시한다. 과거 주문에 표시나 증거를 소급 생성하지 않는다.
- PR140의 `UNKNOWN_STALE` 선기록 경계와 모든 기존 제출 검증을 유지한다. 실행 코어가 신규 REQUESTED 매수의 제출 전 거부를 확인하면 원본 fingerprint를 포함한 중단 증거를 먼저 저장하고 기존 종결 전환을 수행한다. 두 저장 사이에 프로세스가 종료된 경우에도 대사가 가능하다.
- `KisUnsubmittedOrderReconciliationService.propose()`는 관리자 legacy BUY에만 적용한다. 제출 번호·시각·체결·진행 흔적, 미확정 상태, 보유 증거, 다른 계좌 또는 잔존 claim이 있으면 거부한다. 완전한 주문 이력과 신선한 계좌 조회도 필요하다. 수량이 다른 부분 제출이나 거절을 포함해 같은 종목의 브로커 흔적이 있으면 보수적으로 거부한다.
- 원본 주문 전체 fingerprint, 예약 fingerprint, 중단 증거 fingerprint와 목표 상태를 승인 digest에 묶는다. 클라이언트가 전달한 브로커 증거 JSON을 사용하지 않는다.
- 적용에는 활성 관리자, 일치하는 digest, 비어 있지 않은 승인 참조가 필요하다. 동일 계좌 execution mutex 안에서 원본·예약·증거와 KIS를 다시 읽고 CAS로 변경한다. 변경 전후 주문 상태와 승인 주체를 감사 기록에 저장한다.
- 목표 상태는 PR140의 `REJECTED_BY_SAFETY_GATE / not_submitted`다. `CANCELED`를 사용하지 않는다. 원래 요청·응답을 보존하고 예약은 `blocked`로 표시하되 키를 삭제하지 않는다. 기존 accounting과 금액 예약 계산이 이 안전 종결 상태를 제외하므로 날짜 예외는 필요 없다.
- 이 기능은 스케줄러가 자동 호출하지 않는다. 운영 #18은 새 프로토콜과 양성 중단 증거가 없어 현재 도구로 승인할 수 없다. 증거/프로토콜을 임의로 삽입해 우회해서는 안 된다.

### 청산 retry와 timeout

- 정상 모니터링에서 일시적인 positions 조회 실패가 매번 별도의 exit cycle을 생성하고, 재조회에서 빈 잔고를 확인해 `resolved_hold / no_exit_candidate`로 끝나는 흐름을 확인했다. 11/9에는 57건, 장외 `hard_blocked / outside_regular_hours` 5건이었다.
- 최근 300초 이내 동일 인증 계좌의 **빈 목록이 확인됐고**, 미종결 lifecycle과 미확정 SELL이 없는 모니터링 실패에는 새 SELL retry job을 만들지 않는다. 정기 모니터링은 계속한다. 실패한 조회는 여전히 unknown이며 BUY 권한을 부여하지 않는다. 실제 보유, 미확정 청산, 오래된/없는 스냅샷은 기존 retry와 차단을 유지한다. 진입 슬롯의 복구 동작도 유지한다.
- 분리 실행되는 계좌 snapshot retry와 포지션 복구가 최종 결과를 원래 계좌·프로필·날짜·슬롯에 반영한다. 첫 작업의 pending 저장보다 재시도가 먼저 끝나는 경쟁 상황도 보호한다. 완료·timeout 상태는 늦은 결과가 덮어쓰지 못한다.
- 진짜 만료는 슬롯 상태와 `result_json.reason` 모두 timeout으로 일치시키고 직전 분석/재시도 결과는 `last_observed_result`로 보존한다. 600초 매수 창과 720초 작업 제한, 기존 context 취소, 단일 실행 lane 및 execution claim을 유지했다. timeout 예산을 늘리지 않았다.

### 홈 표시

오늘 결정 API는 분석 사유와 계좌별 스케줄러 실행 사유를 분리한다. 슬롯에 저장된 실제 차단/실패를 반영하며 다른 계좌나 프로필의 결과를 섞지 않는다.

홈 카드에서 미완료 진입 한도, 포지션 재조회, 청산 미확정, 계좌 조회 실패, timeout, AI 점수 미달을 각각 설명한다. AI 점수 미달은 HOLD로 표시한다. 종목명, GPT·최종 점수와 원래 reason code도 보존한다. 별도의 실행 차단이 있으면 AI 보류 문구로 덮지 않는다.

## 운영 DB 복제 검증

원본을 SQLite backup API로 **메모리 DB 두 개**에 복제했다. 실제 계좌 인증정보가 들어 있는 복제 파일은 저장하지 않았다. 브로커는 FakeBroker만 사용했다.

| 사례 | 변경 전 체결 / 미완료 / 잔여 | 변경 후 | 의미 |
|---|---|---|---|
| 원본 그대로의 복제본 | 0 / 1 / 0 | 0 / 1 / 0 | #18 증거 부족으로 거부. 운영과 동일한 판단. |
| 독립된 가정 실험 | 0 / 1 / 0 | 0 / 0 / 1 | 메모리 복제본에만 신규 프로토콜 및 검증 가능한 중단 증거를 가정해 관리자 승인 후 안전 종결. 실제 #18 미제출을 입증한 실험이 아니다. |

두 사례 모두 #13·#19 fingerprint를 보존했다. 실제 KIS submit=0, 원본 DB 파일 hash도 동일했다.

## 운영 승인 및 적용 순서

1. 이 PR은 구현·검증까지 수행했다. 커밋·푸시·PR 생성·배포·운영 정합성 복구를 하지 않았다.
2. 배포 검토 시 신규 journal 테이블 생성(`init_db()`의 metadata create 경로)과 기존 PR140 제출 경계가 적용되는지 확인한다. 이번 작업 중 운영 DB에 테이블을 생성하지 않았다.
3. 먼저 읽기 전용 승인안 생성 명령을 실행한다. #18은 현재 아래 명령에서 차단되는 것이 정상이다.

   ```powershell
   .\.venv\Scripts\python.exe scripts/reconcile_unsubmitted_kis_order.py --order-id 18 --admin-user-id 1 --output .tmp/order18-review.json
   ```

4. #18의 제출 부재를 확정할 독립적인 추적/브로커 증거가 추가로 필요하다. 현재 부족한 증거를 승인만으로 대체할 수 없다. 새로운 증거를 받아도 기존 주문에 프로토콜이나 journal을 소급 삽입하지 않고, 그 증거의 신뢰성과 검증 경로를 별도 검토해야 한다.
5. 적격 주문에 대해서만 관리자가 생성된 주문·계좌·fingerprint·종결 상태·digest를 확인하고 승인 참조를 남긴다. 그 후 아래 명시적 적용 명령이 신선한 재조회와 검증을 다시 수행한다. 이 명령은 이번 작업에서 운영 DB에 실행하지 않았다.

   ```powershell
   .\.venv\Scripts\python.exe scripts/reconcile_unsubmitted_kis_order.py --order-id <id> --admin-user-id 1 --apply-plan .tmp/order-review.json --approve-digest <reviewed-digest> --approval-reference <approved-change-reference>
   ```

6. fingerprint 변경, 계좌 claim 점유, 부분 제출 가능성 또는 불완전한 조회가 있으면 중단하고 새 승인안으로 다시 검토한다. 적용 후 accounting·예약 키·감사 로그와 계좌 차단 사유를 확인한다. 이 과정에 재제출·매수·매도·취소는 포함되지 않는다.

## 검증 결과

- 신규 정합성 복구·계좌 분리·부분 제출 거부·재검증·retry·timeout·홈 API 테스트와 필수 두 replay: **93 passed**.
- 홈 관련 집중 검사: **25 passed**.
- 전체 Flutter: **812 passed**. `flutter analyze --no-pub`: **No issues found**.
- 전체 backend pytest: **2,947 passed, 1 skipped**, 24분 56초. PR140~PR143 회귀를 포함한 2,948개 전체 항목을 기존 로컬 pytest-xdist의 4개 프로세스로 실행했다. 각 프로세스는 conftest가 생성한 별도 DB를 사용했다. 생략 1건은 `AUTO_INVEST_DIAGNOSTIC_CLONE`으로 지정하는 별도 과거 운영 백업이 필요한 기존 선택 테스트(`test_operational_backup_reconciles_19_and_diagnoses_13_in_separate_copy`)다. 현재 운영 DB의 메모리 복제 실험은 위와 같이 별도로 완료했다.
- `python -m compileall app`, 운영 도구 컴파일, `git diff --check`: **통과**.
- 기존 사용자 변경 파일 4개의 SHA-256 동일, 원본에 journal 테이블 미생성, 원본 #18 REQUESTED 유지 확인.

## 변경 파일

- `app/db/models.py`: 제출 전 중단 journal 모델.
- `app/services/kis_unsubmitted_order_reconciliation_service.py`, `scripts/reconcile_unsubmitted_kis_order.py`: 승인안·재검증·CAS·감사 및 운영 도구.
- `app/services/automation_profile_buy_scheduler_service.py`, `app/services/kis_automation_execution_core.py`: 신규 주문 프로토콜과 실제 제출 전 중단 증거.
- `app/brokers/kis_account_execution_reader.py`: 대사용 전체/미체결 필터 추가, 홈 기본 체결 필터 보존. 이 파일은 기존 PR143 미커밋 작업을 이어 수정했다.
- `app/services/automation_scheduler_service.py`, `app/services/scheduler_slot_dispatcher.py`: 불필요한 retry 방지 및 부모 슬롯 최종 상태 반영.
- `app/services/automation_today_decision_service.py`, `lib/models/automation_today_decisions.dart`, `lib/features/dashboard/widgets/home_latest_ai_decision_card.dart`: 실제 실행 사유와 AI HOLD 표시.
- `app/tests/integration/test_pr144_reconciliation.py`, `app/tests/integration/test_pr144_scheduler_diagnostics.py`, `test/pr144_home_block_reason_test.dart`: 회귀 검증.

기존 PR143 미커밋 파일과 사용자 변경 `.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py`, 기존 운영 진단 문서를 보존했다. min entry score >=65, possible-order freshness <=10초, cash-only, max positions, 중복·예약·멱등성, daily cap, 장 시간·cutoff, TP/SL, 실행 권한, Kill Switch를 완화하지 않았다.
