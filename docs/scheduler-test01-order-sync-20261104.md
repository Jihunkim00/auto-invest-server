# 관리자 스케줄러 / test01 KIS 주문 동기화 진단

2026-11-04 KST 조사. 운영 DB 변경, KIS 매수·매도·취소, 커밋·푸시·PR 생성은 수행하지 않았다. 실제 계좌 확인은 test01 자격증명을 사용하는 조회와 토큰 발급만 허용한 전송 계층으로 수행했다. 통합 재현에서는 복제 DB와 FakeBroker/FakeKisClient/Fake HTTP만 사용한다.

마스킹한 실제 조회 증거: [scheduler-test01-sync-evidence-20261104.json](scheduler-test01-sync-evidence-20261104.json).

## 1. 정확한 원인

### 관리자 DetachedInstanceError

운영 로그와 `automation_scheduler_slots`의 다음 6건이 모두 일치한다.

| KST 일자 | 슬롯 | 저장된 skip 감사 행 | 최종 슬롯 오류 |
|---|---|---|---|
| 2026-10-31 | 11:20 / 12:20 / 13:30 | #290 / #292 / #294 | scheduler_slot_failed:DetachedInstanceError |
| 2026-11-02 | 11:20 / 12:20 / 13:30 | #296 / #298 / #300 | scheduler_slot_failed:DetachedInstanceError |

모든 감사 행의 원래 결과는 `skipped / active_profile_or_slot_unavailable`이다. 당시 첫 슬롯은 11:20이었다. 현재 프로필의 10:45 / 12:20 / 13:30과 구 11:20을 모두 회귀 재현한다. 현재 프로필 설정만으로 과거 프로필 가용성 판단의 세부 원인을 복원하지는 않는다.

실제 예외 스택: `SchedulerTaskSupervisor.run → SchedulerSlotDispatcher.execute → _run_scheduled_admin_slot → AutomationSchedulerService._run_automation_tick`, 수정 전 1009행의 `getattr(original, 'result', 'failed')`.

`_create_scheduler_skip_log`는 시장 레짐 진단을 `TradeRunLog.response_payload`에 추가하고 `db.commit()`한 뒤 ORM 행을 반환했다. 기본 `expire_on_commit=True` 때문에 행 속성이 만료되고, `_run_automation_tick_impl`의 `finally: db.close()`가 그 행을 분리했다. 바깥 진단 래퍼가 `result`, 이후 `id` 등을 읽으려 해 재조회할 세션이 없었다. 정상적인 차단을 기록한 뒤 기록 처리에서 실패한 것이며, 관찰된 6건을 매수 실패나 재주문 근거로 취급하면 안 된다.

### test01 #19

`owner_user_id=2`, 032640 BUY 2주, 제출 시각 2026-11-04 12:48:00 KST. 운영 DB는 `PENDING / filled_qty=0 / last_synced_at=NULL`, 포지션 lifecycle 없음이다.

주기 동기화는 관리자 클라이언트의 NULL 소유 주문만 조회한다. 사용자 조회 클라이언트에는 체결 이력 조회가 없었고, 사용자 주문 API에는 자기 주문을 동기화하는 경로가 없었다. `PENDING`도 직렬화 결과의 `is_syncable`에서 빠져 있었다. 따라서 제출 결과만 남고 사용자 계좌 체결이 반영되지 않았다. 관리자 조회 범위를 사용자 주문까지 확장해서 해결하면 계좌가 섞이므로 그렇게 변경하지 않았다.

test01 소유 계좌의 실제 주문번호 일치 조회에서 주문일·종목·매수 구분·수량을 확인했다: **주문 2 / 체결 2 / 잔량 0 / 평균 15,680원**. 현재 계좌는 보유 1종목, 미체결 0건이다. 새 read-only 클라이언트의 주문번호 지정 조회도 정확히 1건을 반환했다. 이 증거는 실제 체결 확인이며 운영 DB 갱신과 구분한다.

### 과거 #13 — 별도 진단

028670 BUY 5주, 제출 2026-10-13 12:32:13 KST. 10월 19일 17:12:16 KST의 과거 빈 조회 때문에 `UNKNOWN_STALE / filled_qty=0` 상태였다.

현재 test01 소유 계좌 조회에서는 **10월 13일 5주 전량 체결, 평균 6,560원**을 확인했다. **10월 14일 같은 종목 5주가 평균 7,070원에 전량 매도**된 이력도 있고, 로컬 SELL #14는 이미 FILLED다. #13의 과거 BUY 체결을 확인하더라도 현재 보유 포지션을 다시 만들면 안 된다.

최초 빈 조회의 원인은 **미확정**이다. 당시 소유자 검사가 없던 코드와 계좌 식별이 없는 빈 응답은 남아 있지만, 실제로 어떤 계좌 자격증명으로 조회했는지 입증할 감사 정보가 없다. 현재 동일 계좌에서는 거래소 조건 생략/ALL 및 주문일·주문번호 지정 조건 모두 해당 주문을 반환한다. 거래소 필터 또는 과거 계좌 혼용을 확정 원인으로 주장하지 않는다.

## 2. 수정 파일과 동작

| 파일 | 변경 |
|---|---|
| `app/services/automation_scheduler_service.py` | skip 결과·감사 행 ID를 열린 세션 안에서 일반 값으로 변환. 세션 종료 후 ORM 속성 접근 제거. 별도 세션에서 기존 감사 행에 진단 추가하며 감사 행 중복 생성 방지. |
| `app/services/user_broker_account_service.py` | 사용자 자격증명으로만 read-only 클라이언트 생성. 주문번호 지정 일별 체결 조회, 거래소 ALL, 환경·응답 형태 검증. 연속 페이지 응답은 완료로 가장하지 않고 차단. |
| `app/services/user_kis_order_sync_service.py` | owner/실제 계좌 자격증명/환경/주문번호/주문일/종목/방향/수량/체결가 검증 후 기존 매핑 적용. 현재 보유 수량이 일치할 때만 기존 사용자 포지션 등록 함수를 호출. 불일치·불완전 조회는 수동 검토 진단으로 반환. |
| `app/routes/user_trading.py` | `POST /users/me/trading/orders/{order_id}/sync`. 인증된 일반 사용자의 자기 주문만 조회·갱신. 타인 주문 404, 관리자 세션 403. |
| `app/services/kis_order_account_scope.py` | 조회 전용 검증에서만 `require_enabled=False`를 선택 가능하게 함. 주문 실행 호출의 기본값 True 유지. |
| `app/services/kis_order_sync_service.py` | 제출 후 PENDING 주문을 동기화 가능 상태로 표시. |
| `scripts/inspect_kis_local_order.py` | 읽기 전용 비교 진단에 거래소 조건 및 주문번호 지정 비교 추가. BUY는 별도 owner-scoped 경로로 안내. |
| `app/tests/integration/test_scheduler_session_and_owner_sync_replay.py` | 독립 세션·슬롯 원장·장애 분기·계좌 격리·실제 백업 복제/마스킹한 증거 재생 회귀. |
| `app/tests/test_market_regime_trading_shadow.py` | 내부 skip 반환값의 변경된 dict 계약 확인. 시장 레짐/차단 게이트 검증 유지. |
| `app/tests/support/production_replay_oct28.py` | 과거 슬롯 원장의 시간을 복제본 프로필에 복원. 스냅샷 rewind 시 미래에 생긴 하위 오류·복구 작업과 임시 잠금도 복제본에서 정리. 원본과 운영 정책은 변경하지 않음. |

현재 사용자 전체에 대한 새 주기 동기화 작업을 활성화하지 않았다. 소유자별 단일 주문 동기화 경로를 제공하며 과거 주문을 자동 일괄 정정하지 않는다. 기존 #18은 REQUESTED 상태와 원본 내용을 유지하고 재제출하지 않는다.

새 경로는 조회한 날을 과거 체결 시각으로 꾸미지 않는다. 정확한 체결 시각이 없는 경우 `filled_at`을 발명하지 않고, 기존 제출일을 사용해 일일 거래 횟수 계산에서 과거 거래가 오늘로 이동하지 않게 한다. 매수 체결과 현재 보유 증거가 서로 다르면 체결 사실과 포지션 연결 상태를 별도로 반환한다.

## 3. 회귀 테스트 결과

최종 전체 실행: **2,838 passed, 실패·오류·스킵 0건**, 3,192.36초(53분 12초). 외부 전송 차단 플러그인과 격리 DB를 사용했다. 운영 백업 및 마스킹한 #19/#13 실제 증거를 Fake 응답으로 재생하는 선택적 테스트도 활성화했다.

| 검증 | 최종 결과 |
|---|---|
| `app/tests/integration/test_kis_automation_scheduler_replay.py` | 39 passed |
| `app/tests/integration/test_kis_automation_full_lifecycle_replay.py` | 19 passed |
| 새 세션/슬롯/owner 동기화 회귀 | 57 passed |
| 기존 PR140/PR141 과거 재현 별도 재검증 | 18 passed |
| 전체 backend pytest | 2,838 passed, 실패·오류·스킵 0 |
| `python -m compileall app` | PASS |
| `git diff --check` | PASS |

10:45 / 12:20 / 13:30별 정상 paper 실행, HOLD(진입 점수 64로 차단), BUY(FakeBroker), 분석 실패 및 재호출 멱등성을 검증했다. 별도 세션을 사용하고 `expire_on_commit=True`, `close_resets_only=False`로 세션 재사용이 원래 장애를 가리지 않게 했다. 두 장애 날짜의 skip 분기와 구 11:20 슬롯도 포함한다. 복제본에서 #19를 FILLED/2/0으로 바꾸고 포지션이 정확히 한 번 연결되는지, #13은 실제 과거 체결로 정정하더라도 현재 포지션을 만들지 않는지, 오늘 진입 횟수가 1로 유지되는지 확인했다.

로그와 기계 판독 결과: [최종 pytest 로그](../.tmp/scheduler_order_sync/full_backend_final.log), [JUnit XML](../.tmp/scheduler_order_sync/full_backend_final.xml), [검증 집계](../.tmp/scheduler_order_sync/validation_summary.json). 전체 실행의 12개 경고는 기존 FastAPI/SQLite deprecation 및 기존 strategy_live OpenAPI operation ID 중복 경고다.

첫 전체 실행에서는 기존 10월 28일 운영 DB 재현 15건이 실패했다. 새 회귀 테스트의 실패가 아니었다. 현재 프로필의 첫 슬롯이 11:20에서 10:45로 바뀌어 과거 슬롯을 찾지 못했고, 복제본의 미래 복구 자료가 재사용된 실행 ID에 붙어 재시도 예산을 오염시켰다. 당시 슬롯 원장으로 스케줄을 복원하고 부모·하위 복구 자료를 함께 rewind하도록 테스트 도구를 바로잡았다. 테스트를 삭제하거나 기준을 낮추지 않았다.

안전 기준: 진입 점수 65 이상, possible-order 10초 이내, 현금 주문, 최대 포지션, 예약·중복·멱등성, 일일 거래 한도, 장 시간·cutoff, TP/SL, execution authority를 완화하지 않았다. 사용자 포지션 등록은 기존 함수와 기준을 재사용한다.

## 4. 운영 영향 및 재개 전 확인

1. 변경된 코드 배포/프로세스 재시작 여부와 관리자 활성 프로필·운영 기간·평일/장 시간 및 10:45 / 12:20 / 13:30 슬롯 설정을 확인한다. 과거 failed 슬롯을 자동 재생하지 않는다.
2. #18은 계속 미해결로 남는다. 제출 여부와 기존 예약을 별도 조사하기 전 상태를 정정하거나 새 주문을 제출하지 않는다. 이 차단이 남아 있으면 새 매수도 계속 제한될 수 있다.
3. test01 로그인 세션에서 #19의 최신 주문번호 체결 증거를 다시 확인한 뒤 새 단일 주문 동기화 경로를 호출한다. 원본 DB 쓰기 금지에 따라 이번 작업에서는 운영 호출을 수행하지 않았다. 결과의 `FILLED / 2 / 0` 및 `position_reconciliation.status=linked`, owner=2, entry_order_id=19를 함께 확인한다.
4. #13은 별도 과거 주문 정정으로 취급한다. 최신 체결 이력과 SELL #14를 확인하고, 현재 보유 포지션을 재생성하지 않는지 확인한다. 과거 거래를 오늘의 진입 횟수에 더하지 않는다.
5. 관리자/test01 계좌와 자격증명을 분리해 확인한다. 실제 재개 전 활성 프로필의 TP/SL 및 기존 안전 게이트를 확인한다. 이 수정은 실제 매매 재개나 주문 제출을 실행하지 않는다.

원본 `auto_invest.db`의 작업 전후 SHA-256은 동일하다: `1a427674d81399bda0c0a579c32887e3d556256c3259ea127e75ab811b58122d`. 기존 사용자 변경인 `.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py`는 보존했다.

최종 읽기 전용 확인에서도 운영 #18은 REQUESTED, #19는 PENDING/0/미동기화, #13은 UNKNOWN_STALE/0 상태를 유지한다. 실제 KIS 체결 확인과 복제본 갱신 검증을 운영 적용으로 오해하지 않도록 구분한다.
