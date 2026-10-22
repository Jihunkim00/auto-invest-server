# PR138 test01 로컬 SELL #14 정합성 복구 검증

KIS 과거 이력을 직접 대조한 결과, #14는 테스트 잔재가 아니라 **2026-10-14에 5주 전량 체결된 실제 SELL**이다. 사용자의 명시적 승인 후 2026-10-22 16:10:45 KST에 운영 #14를 `UNKNOWN_STALE → FILLED / 체결 5 / 잔여 0`으로 복구했다. 실제 차단 함수를 읽기 전용으로 재확인하여 `local_unresolved_sell_order` 해제를 확인했다. 자동매매 강제 실행과 신규 실주문은 0회다.

## 사용자 승인 후 운영 복구

[마스킹한 운영 복구 증거](pr138-order14-approved-repair.json)에 승인 참조, 직전 KIS 조회, 변경 전후, 감사 로그, 읽기 전용 확인 결과를 저장했다.

| 항목 | 결과 |
|---|---|
| 직전 KIS 주문·체결 조회 | 2026-10-22 16:10:44.005989 KST, 전체 거래소·전체 방향·전체 체결 상태, 1페이지 완료 |
| 주문 대조 | test01 전용 live 자격증명, 동일 주문번호 `***2100`·주문일·종목·SELL·주문 수량 5주 일치 |
| 실제 체결 | 5주 전량 체결, 잔여 0, 평균 7,070원 |
| 직전 잔고·미체결 조회 | 16:10:44.039329 KST, 신뢰성 확인된 보유 0종목·미체결 0건 |
| 운영 적용 | 16:10:45.284611 KST, 주문 #14 한 행 UPDATE + 감사 로그 #233 한 행 INSERT |
| 복구 결과 | FILLED, 체결 5 / 잔여 0, 평균 체결가 7,070원, 동기화 오류 해제 |
| 감사 로그 | owner 2 / order 14 / `approved_order_reconciliation` / `broker_terminal_order_verified`, 승인 참조·변경 전후·조회 근거 보존 |
| 기존 자료 보존 | 원본 요청·응답·주문번호·생성·제출 시각 보존, 기존 inquiry 내용 보존 후 승인 근거 추가, 불명인 체결 시각과 손익은 생성하지 않음 |
| 변경 범위 검증 | 쓰기 잠금 안에서 56개 테이블의 승인 대상 외 기존 51,259행 해시 동일, 관리자·test02 자료 포함 |
| 읽기 전용 재확인 | 16:10:46.601598 KST, SQLite `mode=ro/query_only=ON`, 실제 `position_management_block_reason` 결과 `None` |
| 강제 스케줄러 / BUY / 실주문·취소 | 모두 0회 |

첫 운영 시도에서는 추가한 변경 범위 검사가 SQLite `INSERT ... RETURNING`의 결과 소비 전 cursor rowcount 0을 실패로 해석하여 커밋 전에 롤백했다. 직후 운영 #14가 원래 상태이고 복구 감사 행이 0건임을 읽기 전용으로 확인했다. 검사에서는 실제 삽입 행과 `changes()`를 대조하도록 조정했고, 격리된 DB와 Fake 이력·계좌로 전체 작업을 검증했다. 이후 KIS 이력·잔고·미체결을 새로 조회한 위 두 번째 시도에서만 커밋했다. 애플리케이션 코드는 변경하지 않았다.

운영 복구 후 분석이나 BUY를 강제로 실행하지 않았다. 다음 정상 슬롯에서 기존 스케줄러와 점수·계정 리스크·Kill Switch·시장 시간·최종 제출 검사가 판단한다. 과거 슬롯을 재실행하거나 프로필·운영 설정을 변경하지 않았다. 아래 최초 조사와 테스트 DB 결과는 복구 전 근거로 보존한다.

## 읽기 전용으로 확인한 사실

확인 시각: 2026-10-22 00:41:52 KST. [마스킹한 조회 증거](pr138-order14-readonly-evidence.json)에 로컬 기록, KIS 응답의 필요한 필드, 호출한 조회 경로와 변경 건수를 저장했다. SQLite `mode=ro`, `query_only=ON`을 사용했다. HTTP는 토큰 발급과 잔고·미체결·과거 이력 조회만 허용하고 리다이렉트를 금지했다.

| 항목 | 확인 결과 |
|---|---|
| 주문 / 소유자 | #14 / test01, `owner_user_id=2`, KIS KR |
| 생성 시각 | 2026-10-14 11:30:21 KST |
| 제출 시각 | 2026-10-14 11:30:21.621677 KST |
| 출처 | `user_scheduler`, automatic, 슬롯 11:30 |
| 매도 근거 기록 | `take_profit_triggered`, signal #78 |
| 종목 / 수량 / 유형 | 028670 / SELL 5주 / 시장가 |
| 프로필 | 기존 행의 `profile_id`, `profile_key` 모두 NULL |
| 내부 상태 | `UNKNOWN_STALE`, 체결 0, 잔여 5 |
| 브로커 상태 / 동기화 오류 | `submitted` / `not_found_in_inquiry`, `kis_order_not_found_in_inquiry` |
| 마지막 로컬 동기화 | 2026-10-19 17:12:17.794338 KST |
| 당시 저장된 조회 요약 | 2026-10-14 하루 조회, count=0, rt_cd=0, msg_cd=KIOK0560; 원본 계좌·HTTP 요청·전체 응답은 보존되지 않음 |
| KIS 주문번호 | 끝 4자리 `***2100`; 원문은 공개 로그·보고서에서 제외 |
| 원본 응답 | 주문번호 존재, `status=submitted`, `filled_qty=0`, 제출 시각 존재 |
| 연결 실행 로그 | #186, owner 2, live, `user_exit_order_submitted`, 당시 `broker_submit_called=true`, `real_order_submitted=true` |
| 연결 신호 | #78, owner 2, 동일 종목 SELL, user_scheduler, submitted, related_order_id=14, approved_by_risk=true |
| 로컬 포지션 생명주기 | test01 행 0건; 이번 복구로 과거 매수·포지션을 만들어내지 않음 |
| 과거 KIS 대조 | 주문번호·주문일·종목·SELL·수량 일치, 주문 시각 11:30:21 |
| 실제 체결 / 잔여 | `tot_ccld_qty=5`, `rmn_qty=0`, 평균 7,070원, 체결금액 35,350원 |
| 현재 KIS 상태 | 신뢰성 확인된 보유 0종목, 미체결 0건 |
| 이력 조회 범위 | 2026-10-14~2026-10-22, 전체 방향·전체 체결 상태·전체 거래소, 1페이지, 전체 1건 |
| 조사 중 신규 실주문 / DB 변경 | **0 / 0** |

현재 미체결 0건을 과거 미제출의 근거로 사용하지 않았다. 위 KIS 이력 자체가 과거 SELL 제출·체결의 근거다. 조회 기간 내 BUY는 0건이며, 그 이전 매수나 종목 입고 경위는 이번 조회로 확인할 수 없다. `ord_tmd`는 주문 시각이므로 이를 체결 시각으로 쓰지 않는다.

원본 요청의 `mode=alpaca_live`는 provider=KIS와 불일치하는 과거 라벨이다. 원본 감사 자료이므로 수정하지 않는다. 과거 동기화가 이 주문을 놓친 최초 원인은 `root_cause_unconfirmed`로 유지한다. 현재 공식 조회 예제의 live 이력 TR은 `TTTC0081R`이며 이번 읽기 전용 조사에서도 이를 사용했다. 기존 동기화의 구형 TR·조회 조건이 원인인지는 당시 원본 응답 없이 확정할 수 없다. [KIS 공식 일별 주문·체결 조회 예제](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py)

00:57 KST 추가 [읽기 전용 조회 비교](pr138-order14-inquiry-comparison.json)에서는 `TTTC0081R/KRX`, `TTTC8001R/거래소 생략`, `TTTC8001R/ALL` 모두 #14를 1건 반환했다. 따라서 구형 TR이나 거래소 조건만을 누락 원인으로 단정할 수 없다.

## 승인받아 적용한 복구안

범위는 **owner 2의 주문 #14 한 행과 해당 복구 감사 로그 1건**이다. 실행 경로에 자동 복구를 연결하지 않았다.

| 필드 | 복구 전 | 승인 후 적용 |
|---|---|---|
| `internal_status` | UNKNOWN_STALE | FILLED |
| `filled_qty` / `remaining_qty` | 0 / 5 | 5 / 0 |
| `avg_fill_price` / `filled_avg_price` | 미확정 | 7,070 / 7,070 |
| `broker_status` / `broker_order_status` | submitted / not_found_in_inquiry | filled / filled |
| `sync_error` / `error_message` | 과거 조회 실패 | 현재 오류 해제, 이전 값은 감사 로그에 보존 |
| `last_synced_at` | 과거 조회 시각 | 재검증 시각 |
| `last_sync_payload` | 과거 inquiry | 기존 내용 보존 + 승인·근거·해시 추가 |
| 원본 request / response / 주문번호 / 생성·제출 시각 | 기존 기록 | 그대로 보존 |
| `filled_at` / 손익 / 과거 포지션 | 불명 또는 기존 값 | 체결 시각·취득 원가·손익을 추정하여 생성하지 않음 |

`apply_verified_reconciliation`은 승인 참조가 없으면 거부한다. 승인 후에도 실제 KIS 이력과 현재 계좌를 다시 조회하고, 계정·주문번호·날짜·방향·종목·수량·전량 체결·조회 완전성을 검증해야 한다. 검증 근거가 300초를 초과하거나 주문의 기존 필드가 달라졌으면 적용하지 않는다. 단일 트랜잭션에서 기존 값이 일치하는 경우에만 갱신하고, 동일 소유자의 `TradeRunLog(mode=kis_order_reconciliation)`에 변경 전후·승인 참조·검증 근거를 남긴다. 기존 행을 삭제하지 않는다.

이 유지보수 검증의 300초 제한은 주문 실행의 10초 possible-order 신선도 제한과 별개다. 신규 BUY는 기존 점수·리스크·시장·권한·10초 신선도·중복·최종 제출 검사를 모두 다시 통과해야 한다. 과거 슬롯은 재실행하지 않는다.

## 격리된 테스트 DB의 복구 전후

[전체 시뮬레이션 기록](pr138-order14-repair-simulation.json)은 실제 리스크 엔진과 실제 스케줄러·분석·주문 동기화·포지션 생명주기 코드를 사용한다. Fake Account/Market Data/Broker와 GPT Mock만 주입하며 실제 네트워크와 실제 submit 메서드를 모두 차단한다.

| 단계 | 복구 전 test01 | 테스트 DB에서 승인 복구 후 test01 |
|---|---|---|
| 실행 슬롯 | 11:30 | 다음 유효 슬롯 13:30 |
| Position Management | local_unresolved_sell_order, #14, UNKNOWN_STALE, 잔여 5 | entry_scan |
| Watchlist / Profile | NOT_REACHED | 200 / 50 |
| A / C / GPT | NOT_REACHED | A Top 5 / C65 PASS / GPT Mock 5건 완료 |
| GPT60 / Final65 | NOT_REACHED | PASS / PASS |
| 실제 계정 Risk | NOT_REACHED | 실제 엔진 통과 |
| Fake BUY / FILLED | 0 / 0 | 1 / 1 |
| 신규 포지션 생명주기 | 0 | 소유자 2의 open 1건 |
| 실제 KIS Submit | 0 | 0 |

11:30 동시 실행에서 관리자와 test02는 각자 정상 BUY/FILLED를 완료했다. #14 복구 직전·직후와 test01의 다음 슬롯 실행 후에도 두 계정 주문의 해시가 동일하다. 복구한 과거 SELL은 오늘의 일일 거래 횟수에 포함되지 않는다.

복구 관련 통합 테스트 22개와 읽기 전용 보호 테스트 7개를 추가했다. 다음 경우에는 복구를 거부하고 원래 행을 유지한다: 이력 누락·중복·불완전 페이지, 소유자·계정·종목·방향·날짜 불일치, 오래된 근거, 활성 SELL, 불확실 주문, 신뢰할 수 없는 계좌, 부분 체결, 수량 불일치·NaN, 체결가 누락, 승인 없음, 조회 후 행 변경. 별도 종료 주문 검증은 체결 없는 취소·거절을 FILLED로 바꾸지 않는지도 확인한다.

`local_unresolved_sell_order` 로그에는 주문 ID·소유자·상태·출처·잔여 수량·확인 시각을 남긴다. 진단 결과에는 마지막 브로커 동기화 시각과 마스킹한 주문번호도 포함한다. 활성 매도와 불확실 주문의 기존 매수 차단을 유지한다.

## 검증과 운영 상태

최종 전체 실행에서 **2,674 passed, 실패·오류·스킵 0**을 확인했다. 소요 시간은 2,025.59초다. 아래 개별 검증은 전체 실행에 포함되며, 계정별 결과와 차단 매트릭스는 [최신 리스크 검증 보고서](pr138-account-risk-gate-verification.md)에 기록한다.

| 검사 | 최종 결과 |
|---|---|
| 전체 backend pytest | 2,674 passed |
| 필수 scheduler replay | 39 passed |
| 필수 full lifecycle replay | 19 passed |
| 세 계정 실제 리스크 매트릭스 | 69 passed |
| #14 복구 통합 / 읽기 전용 보호 | 22 / 7 passed |
| 계좌 데이터 및 최신 Kill Switch 검증 | 9 passed |
| python -m compileall app | exit 0 |
| git diff --check | exit 0 |
| 사용자 변경 파일 | .metadata, config/watchlist_kr.yaml, daily_ops_readonly.py 해시 동일 |
| 승인 전 운영 #14 재확인 | 원본 해시 동일, UNKNOWN_STALE / 체결 0 / 잔여 5, 복구 감사 행 0 |
| 승인 후 운영 #14 재확인 | FILLED / 체결 5 / 잔여 0, 복구 감사 #233, 로컬 SELL 차단 없음 |

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests -q -p app.tests.no_external_transport --tb=short --basetemp=.tmp/pr138_release_verified -p no:cacheprovider --junitxml=.tmp/pr138_release_verified.xml
.\.venv\Scripts\python.exe -m compileall app
git diff --check
```

| 추가 파일 | 목적 |
|---|---|
| app/services/kis_order_reconciliation_service.py | 근거·승인·기존 행 해시에 묶인 단일 주문 복구, 원본 및 감사 이력 보존 |
| scripts/inspect_kis_local_order.py | 운영 SQLite 읽기 전용 조사, 소유자 전용 KIS 조회 전송기와 완전한 과거 이력 수집 |
| app/tests/integration/test_pr138_order14_reconciliation.py | 복구 전후 실제 분석 경로, 계정 격리, 승인·상태·근거 오류 차단 |
| app/tests/test_kis_order_reconciliation_readonly.py | DB 쓰기·실제 주문 URL 차단 및 이력 연속 조회 실패 검증 |
| 이 보고서와 관련 JSON 4개 | 마스킹한 실제 대조·조회 비교·테스트 복구·승인 후 운영 적용 결과를 분리하여 보존 |

운영 #14는 사용자 승인 후 `FILLED`로 복구했고, #14 때문에 발생하던 로컬 미해결 SELL 차단이 해제됐음을 읽기 전용으로 확인했다. 운영 DB 변경은 #14와 새 감사 로그 #233에 한정했다. 실제 주문·취소·자동매매 강제 실행·서버 재시작·운영 설정 변경은 수행하지 않았다. 과거 #14의 실주문 사실과 이번 작업의 실제 submit 0회를 구분한다.
