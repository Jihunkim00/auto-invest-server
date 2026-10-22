# PR138 계정별 실제 리스크 엔진 및 게이트 검증

운영 DB와 실계좌를 사용하지 않고 격리된 테스트 DB, Fake Account/Market Data/Broker, GPT Mock으로 검증했다. 실제 운영 Risk Engine을 `Mock(wraps=실제 메서드)`로 관찰하며 승인값을 대체하지 않았다.

게이트 checked_at과 scheduler_slot은 재현용 가상 시계의 값이며 실제 과거 슬롯에 주문을 소급 제출하지 않았다.

| 계정 | 전체 판정 / 고유 게이트 | PASS | BLOCK | FAILED | NOT_REACHED | 실제 Risk 호출 | Fake BUY / FILLED | 실제 KIS Submit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| admin | 39 / 20 | 39 | 0 | 0 | 0 | 2 | 1 / 1 | 0 |
| test01 | 40 / 20 | 40 | 0 | 0 | 0 | 2 | 1 / 1 | 0 |
| test02 | 40 / 20 | 40 | 0 | 0 | 0 | 2 | 1 / 1 | 0 |

각 계정에서 공통 Watchlist 200 → 계정 Profile Watchlist 50 → 실제 A Top 5 → C65 → GPT Mock 완료 → GPT60 → Final65 → 실제 계정 리스크 → 전역 안전 검사 → Broker Preflight → Fake BUY/FILLED → 포지션 생성을 확인했다. 세 계정은 같은 가상 11:30 슬롯에서 동시에 실행했다.

A 점수는 상위 5종목을 정하는 상대 순위에 사용한다. 진입 기준은 C≥65, GPT≥60, Final≥65이며 낮추지 않았다.

| 계정 | A Top 5 (종목:실제 점수) | C 점수 / C65 | GPT 점수 / GPT60 | Final 점수 / Final65 |
|---|---|---|---|---|
| admin | 000100:44.0, 000150:44.0, 000240:44.0, 000250:44.0, 000270:44.0 | 81.67, 81.67, 81.67, 81.67, 81.67 / PASS | 70.0, 70.0, 70.0, 70.0, 70.0 / PASS | 78.75, 78.75, 78.75, 78.75, 78.75 / PASS |
| test01 | 000100:44.0, 000150:44.0, 000240:44.0, 000250:44.0, 000270:44.0 | 81.67, 81.67, 81.67, 81.67, 81.67 / PASS | 70.0, 70.0, 70.0, 70.0, 70.0 / PASS | 78.75, 78.75, 78.75, 78.75, 78.75 / PASS |
| test02 | 000100:44.0, 000150:44.0, 000240:44.0, 000250:44.0, 000270:44.0 | 81.67, 81.67, 81.67, 81.67, 81.67 / PASS | 70.0, 70.0, 70.0, 70.0, 70.0 / PASS | 78.75, 78.75, 78.75, 78.75, 78.75 / PASS |

| 차단 조건 | 관리자 | test01 | test02 |
|---|---|---|---|
| C65 미달 | 검증 PASS · `C65` BLOCK / `c_score_below_threshold` · BUY 0 | 검증 PASS · `C65` BLOCK / `c_score_below_threshold` · BUY 0 | 검증 PASS · `C65` BLOCK / `c_score_below_threshold` · BUY 0 |
| GPT60 미달 (실제 0점) | 검증 PASS · `GPT60` BLOCK / `gpt_buy_score_below_threshold` · BUY 0 | 검증 PASS · `GPT60` BLOCK / `gpt_buy_score_below_threshold` · BUY 0 | 검증 PASS · `GPT60` BLOCK / `gpt_buy_score_below_threshold` · BUY 0 |
| Final65 미달 | 검증 PASS · `FINAL65` BLOCK / `below_profile_buy_threshold` · BUY 0 | 검증 PASS · `FINAL65` BLOCK / `below_profile_buy_threshold` · BUY 0 | 검증 PASS · `FINAL65` BLOCK / `below_profile_buy_threshold` · BUY 0 |
| 현금 부족 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `buying_power_unavailable` · BUY 0 | 검증 PASS · `ACCOUNT_SNAPSHOT_RISK` BLOCK / `buying_power_unavailable` · BUY 0 | 검증 PASS · `ACCOUNT_SNAPSHOT_RISK` BLOCK / `buying_power_unavailable` · BUY 0 |
| 프로필 최대 포지션 비중 | 검증 PASS · `ENTRY_DECISION` BLOCK / `simulated_quantity_zero` · BUY 0 | 검증 PASS · `SIZING` BLOCK / `quantity_invalid` · BUY 0 | 검증 PASS · `SIZING` BLOCK / `quantity_invalid` · BUY 0 |
| 일일 거래 한도 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `daily_trade_limit_hit` · BUY 0 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `max_daily_trades_reached` · BUY 0 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `max_daily_trades_reached` · BUY 0 |
| 일일 최대 손실 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `daily_loss_limit_hit` · BUY 0 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `daily_loss_limit_reached` · BUY 0 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `daily_loss_limit_reached` · BUY 0 |
| 계정 Kill Switch | 검증 PASS · `ACCOUNT_AUTHORITY` BLOCK / `user_kill_switch_enabled` · BUY 0 | 검증 PASS · `ACCOUNT_AUTHORITY` BLOCK / `user_kill_switch_enabled` · BUY 0 | 검증 PASS · `ACCOUNT_AUTHORITY` BLOCK / `user_kill_switch_enabled` · BUY 0 |
| 전역 Kill Switch | 검증 PASS · `GLOBAL_SAFETY` BLOCK / `global_kill_switch_enabled` · BUY 0 | 검증 PASS · `GLOBAL_SAFETY` BLOCK / `global_kill_switch_enabled` · BUY 0 | 검증 PASS · `GLOBAL_SAFETY` BLOCK / `global_kill_switch_enabled` · BUY 0 |
| 활성 매도 주문 | 검증 PASS · `POSITION` BLOCK / `broker_active_sell_order` · BUY 0 | 검증 PASS · `POSITION` BLOCK / `broker_active_sell_order` · BUY 0 | 검증 PASS · `POSITION` BLOCK / `broker_active_sell_order` · BUY 0 |
| 주문 상태 불확실 | 검증 PASS · `POSITION` BLOCK / `order_status_unverified` · BUY 0 | 검증 PASS · `POSITION` BLOCK / `order_status_unverified` · BUY 0 | 검증 PASS · `POSITION` BLOCK / `order_status_unverified` · BUY 0 |
| 시장 종료 | 검증 PASS · `MARKET_SESSION` BLOCK / `market_session_closed` · BUY 0 | 검증 PASS · `MARKET_SESSION` BLOCK / `market_closed` · BUY 0 | 검증 PASS · `MARKET_SESSION` BLOCK / `market_closed` · BUY 0 |
| 11초 경과 계좌 데이터 | 검증 PASS · `KIS_SNAPSHOT` BLOCK / `account_snapshot_stale` · BUY 0 | 검증 PASS · `KIS_SNAPSHOT` BLOCK / `account_snapshot_stale` · BUY 0 | 검증 PASS · `KIS_SNAPSHOT` BLOCK / `account_snapshot_stale` · BUY 0 |
| 동일 방향 재진입 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `same_direction_reentry_limit_reached` · BUY 0 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `same_direction_reentry_limit_reached` · BUY 0 | 검증 PASS · `ACCOUNT_RISK` BLOCK / `same_direction_reentry_limit_reached` · BUY 0 |
| 진입 마감 | 검증 PASS · `ENTRY_WINDOW` BLOCK / `entry_window_closed` · BUY 0 | 검증 PASS · `ACCOUNT_SNAPSHOT_RISK` BLOCK / `after_no_new_entry_time` · BUY 0 | 검증 PASS · `ACCOUNT_SNAPSHOT_RISK` BLOCK / `after_no_new_entry_time` · BUY 0 |
| 계좌 데이터 오류 | 검증 PASS · `KIS_SNAPSHOT` BLOCK / `account_snapshot_invalid` · BUY 0 | 검증 PASS · `KIS_SNAPSHOT` BLOCK / `account_snapshot_invalid` · BUY 0 | 검증 PASS · `KIS_SNAPSHOT` BLOCK / `account_snapshot_invalid` · BUY 0 |

차단 케이스에서는 Broker Preflight·최종 Submit·BUY 게이트가 모두 NOT_REACHED이고 Fake FILLED도 0이다. C/GPT/Final 점수와 기준, 최초 차단 데이터는 JSON의 각 계정·슬롯 `gates`와 `first_blocked_gate`에 저장했다. 실제 GPT 0점은 BLOCK/0으로, 미실행은 NOT_REACHED/null로 분리한다.

최대 포지션 비중 케이스는 실제 비중 제한으로 허용 예산이 1주 가격 미만이 되도록 구성했다. 실제 Risk가 계산한 상한을 적용한 뒤 관리자 simulated_quantity_zero, 사용자 quantity_invalid로 중단한다. 리스크 엔진의 예산 계산 통과와 최종 주문 수량 차단을 구분해 기록했다.

KIS 잔고 응답에서 선택 필드 buying_power/orderable_cash가 null인 정상 계좌도 세 계정 모두 실제 Risk와 별도 Broker Preflight를 거쳐 Fake BUY/FILLED 1건씩 완료했다. 현금이나 제출 직전 possible-order 검증은 생략하지 않는다.

세 계정 각각에서 실제 Risk 2회와 Broker Preflight를 통과한 뒤 계정/전역 Kill Switch를 켜도 최종 제출 재검사가 BUY/FILLED를 0건으로 차단했다. 별도 연결로 설정이 바뀌었을 때 이전 ORM 캐시를 재사용하지 않는 검사도 검증했다.

| 계정 간 격리 | 결과 |
|---|---|
| 관리자 일일 손실 BLOCK → test01/test02 판단 유지 | PASS |
| test01 일일 손실 BLOCK → 관리자/test02 판단 유지 | PASS |
| test02 일일 거래 제한 → 관리자/test01 판단 유지 | PASS |
| test01 KIS API 오류 → 관리자/test02 정상 실행 | PASS |
| test01 Broker 및 DB 활성 주문 → 타 계정 중복 판정에 영향 없음 | PASS |
| 전역 Kill Switch → 전체 계정 BUY 0 | PASS |
| 세 계정 동시 슬롯 → 독립 리스크·신호·주문·포지션·로그 | PASS |
| 사용자 주문에 관리자 프로필 태그 혼입 → 관리자 손실/거래 집계에서 제외 | PASS |

SELL은 기존 정책을 유지한다. 관리자 TP/SL은 필수 lifecycle replay에서 확인하며, test01/test02는 신규 BUY 현금 부족·진입 마감 조건에서도 손절/익절 SELL 각 1회, BUY 0회를 별도로 검증했다. 계정 Kill Switch와 기존 SELL 권한 제한은 우회하지 않는다.

변경 사항: 사용자 BUY 전역 Kill Switch 재검사, 실제 계정별 동일 방향 재진입 제한, 관리자 성과 집계의 owner 분리, 0원 BUY 리스크 승인 차단, 계좌 데이터 오류/최신성 검증, 중복 근거 및 미확인 상태의 reason 분리, 슬롯별 구조화 게이트 감사 로그와 읽기 전용 진단 출력이다.

| 변경 파일 | 이유 |
|---|---|
| automation_run_diagnostics.py | 계정·프로필·슬롯별 실제 게이트 결과, 기준·점수·이유·시간·미실행 상태 저장 |
| automation_entry_safety.py | BUY 전역·계정 Kill Switch, 계좌 최신성 및 숫자 검증; 선택 금액 null과 오류 구분 |
| automation_scheduler_service.py | 관리자 실제 경로 관측 및 조기 차단까지 별도 감사 로그 저장 |
| user_auto_trading_scheduler_service.py | 사용자 소유권·슬롯별 관측, SELL 우선 후 BUY 데이터 검증, API 오류 근거 보존 |
| kis_watchlist_preview_service.py | 실제 A/C/GPT/Final 계산 결과 관측 |
| profile_aware_dry_run_auto_buy_service.py | 실제 최종 후보 판단 관측 |
| user_risk_state_service.py | 실제 소유자별 완료 진입 횟수·동일 방향 재진입 제한 및 리스크 호출 관측 |
| strategy_performance_service.py | 관리자 리스크 집계 및 프로필 복리 계산에서 다른 소유자 주문 제외 |
| strategy_risk_budget_service.py | 관리자 실제 예산·손익의 계정 격리, 재진입·계정 Kill Switch, 주입 시계 정합성 |
| target_aware_risk_service.py | 실제 리스크 판정 관측 및 0원 BUY 승인 차단 |
| user_trading_execution_service.py | 실제 사용자 리스크 재검사, 전역 Kill Switch 및 제출 전 신선도·중복 근거 관측 |
| kis_automation_execution_core.py | 최종 BUY 안전 게이트·중복 상태 구분·실제 preflight 및 브로커 응답 관측 |
| automation_profile_buy_scheduler_service.py | 실제 차단 이유와 예산·수량 제한 관측 |
| kis_order_account_scope.py | 미해결 로컬 SELL의 주문·소유자·출처·잔여량·확인 시각을 안전하게 기록 |
| diagnose_user_auto_trading.py | 저장된 게이트와 중복 근거를 DB 읽기 전용으로 출력 |
| test_pr138_account_risk_gate_matrix.py / test_automation_entry_safety.py | 세 계정 실제 리스크·독립 차단·SELL·동시 실행·선택 금액 검증 |
| 기존 관련 테스트 8개 파일 | 가상 시계·검증 가능한 Fake 주문·새 사유·감사 행·기존 관리자 skip 반환 형식을 명시하고 전역 Kill Switch 실차단을 검증 |
| export_pr138_risk_verification.py / 보고서 JSON·Markdown | 통과한 전체 pytest 산출물만 집계하고 최초 차단 사유를 검증 |

주문 #14의 실제 이력 조사·사용자 승인 후 운영 FILLED 복구·별도 테스트·읽기 전용 차단 해제 확인은 [정합성 복구 보고서](pr138-order14-reconciliation.md)에 기록한다. 복구 작업에서 자동매매 강제 실행과 신규 실주문은 0회다.

관리자 기존 주문의 NULL 소유권은 보존했다. 게이트 판정 수에는 후보별 5회 점수 검사와 제출 직전 재검사가 포함된다. 점수 관측의 duration_ms는 실제 Preview 단계 합계이고 checked_at은 결과 관측 완료 시각이다. 완전한 게이트 JSON은 같은 이름의 `.json` 파일에 있다.

전체 백엔드 pytest: **2674 passed**, 실패/오류/스킵 0. 리스크 검증 파일: 69 passed. 필수 scheduler/lifecycle replay, compileall, git diff --check 결과는 작업 완료 보고에 함께 기록한다.

실제 KIS 주문 제출 0회. 운영 DB 수정, 서버 재시작, 실제 취소/주문, 운영 설정 변경은 수행하지 않았다.
