# PR143 후속 — 실제 KIS 계좌 체결 조회와 거래 내역 가독성

`pr143-home-compact-trade-history`에서 최초 PR143 압축 레이아웃을 유지하면서 거래 내역의 원천을 KIS 계좌 조회로 교체했다. 커밋·푸시·PR 생성은 수행하지 않는다.

## 기존 0건의 원인과 실제 조회 결과

기존 `GET /trading/fills?provider=kis`는 `orders`의 `last_sync_payload.matched_order` 및 `inquiry`가 검증 가능한 로컬 주문만 표시했다. KIS 계좌 전체를 조회하지 않았으므로 앱 밖의 매매, 미동기화 주문, 로컬 체결 증거가 없는 거래는 빠졌다. 주문 상태만 FILLED로 바꾸는 방식으로 해결할 문제가 아니었다.

2026-11-09 KST에 원본 SQLite를 **mode=ro + query_only**로 열고 실제 KIS 조회를 비교했다. 숫자는 해당 조회 시점 기준이다.

| 계정 | 기간 | 기존 로컬 조회 | 실제 KIS 계좌 조회 |
| --- | --- | ---: | ---: |
| 관리자 | 오늘 | 0 | 0 |
| 관리자 | 1주 | 0 | 0 |
| 관리자 | 1개월 | 0 | 0 |
| 관리자 | 1년 | 0 | 21 |
| test01 | 오늘 | 0 | 1 |
| test01 | 1주 | 0 | 2 |
| test01 | 1개월 | 0 | 4 |
| test01 | 1년 | 0 | 4 |

test01의 1주 조회에서 **2026-11-04, 032640 매수 2주, 평균 15,680원**을 확인했다. 1개월·1년 조회에서는 **2026-10-13 028670 매수 5주**, **2026-10-14 같은 종목 매도 5주**도 확인했다. 주문 시각을 체결 시각으로 바꾸지 않았으며, 정확한 체결 시각이 없는 행은 날짜만 표시한다.

관리자의 오늘·1주·1개월은 실제 계좌에서도 0건이었다. 관리자의 1년 내역 21건은 관리자 자격증명으로 조회한 별도 계좌 결과다. test01 결과를 관리자 내역으로 합산하지 않는다.

실계좌 검증 전후 **원본 DB 파일 SHA-256과 주문 #13·#18·#19의 상태·체결 수량·동기화 자료가 동일**했다. 관리자 인증 토큰은 임시 메모리 DB, 사용자 인증 토큰은 기존 메모리 토큰 관리자에만 보관했다. 주식 주문 제출·매도·취소 요청은 없었다.

검증 자료에는 계좌번호·appkey·appsecret·access_token·원본 응답을 저장하지 않았다. `.tmp/pr143-followup-live-read-evidence.json`에는 계정 구분, 기간, 성공/완전성, 건수와 요청 사례의 일치 여부만 있다. `.tmp/pr143-followup-source-comparison.json`에는 위 표의 건수만 있다.

## 조회 구조와 공식 규격

홈 KIS 조회는 다음 두 인증 API를 사용한다.

- 관리자: `GET /kis/account/executions?period=day`
- 일반 사용자: `GET /users/me/trading/executions?period=day`

관리자 API는 `require_admin`을 거쳐 기존 환경 설정의 관리자 `KisClient`를 사용한다. 일반 사용자 API는 `require_regular_user`를 거쳐 로그인 사용자 ID로 **기존 `UserBrokerAccountService.get_kis_read_only_client()`**를 호출한다. DB에 저장된 해당 사용자의 자격증명을 기존 암호화 경로로 복호화하여 계좌·상품·환경을 지정한다. 계좌번호나 사용자 ID를 요청에서 받아 조회 범위를 바꾸지 않는다. 두 API는 서로의 역할을 403으로 차단한다.

새 `inquire_account_executions_page()`는 전체 계좌의 체결 전용 GET이다. 기존 `inquire_daily_order_executions()`와 `UserKisOrderSyncService`의 PR142 주문번호별 동기화 경로는 변경하지 않았다. KIS 홈은 로컬 `orders`를 조회하지 않는다. 기존 `/trading/fills`는 이전 로컬 조회 및 Alpaca 호환 경로로 남아 있으며 새 KIS 홈에서는 호출하지 않는다.

[현재 KIS 공식 샘플](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py)의 실행 코드에 맞춰 TR ID를 적용했다. 요청서의 이전 ID 대신 현행 ID를 사용하기로 사용자 답변에서 확인했다.

| 환경 | 최근 구간 | 과거 구간 |
| --- | --- | --- |
| LIVE | `TTTC0081R` | `CTSC9215R` |
| PAPER | `VTTC0081R` | `VTSC9215R` |

경로는 `/uapi/domestic-stock/v1/trading/inquire-daily-ccld`, 매수·매도 전체는 `SLL_BUY_DVSN_CD=00`, 체결 전용은 `CCLD_DVSN=01`이다. `EXCG_ID_DVSN_CD=ALL`로 KRX/NXT/SOR 범위를 요청한다. 주문번호 필터는 비운다. 응답 헤더 `tr_cont`의 M/F는 다음 페이지를 뜻하며, 응답의 FK/NK를 다음 요청에 전달하고 요청 헤더는 N으로 바꾼다.

3개월 저장 구간 경계는 [공식 legacy 샘플의 월 단위 설명](https://github.com/koreainvestment/open-trading-api/blob/main/legacy/Sample01/kis_domstk.py)을 따라 해당 월에서 3개월 전 **월초**로 정했다. 2026-11-09의 경계는 2026-08-01이다. 현재 공식 함수는 inner/before 선택을 호출자에게 맡기므로 이 경계 계산은 서비스가 명시적으로 담당한다. 앞뒤 날짜를 빠뜨리거나 중복 합산하지 않는다.

## 기간·완전성·호출 예산

`day/week/month/year`는 오늘을 포함한 최근 **1/7/30/365개 KST 날짜**다. 시작일 00:00부터 현재까지를 조회한다. 오늘은 당일만 요청한다. 1주·1개월·1년은 선택할 때 새로 조회하며 홈 기본 로딩에 1년 조회를 포함하지 않는다.

- 최근·과거 구간을 나누고, 각 요청 구간은 최대 30일로 제한한다.
- 오래된 내역은 공식 샘플의 장 종료 후 조회 권고를 반영해 평일 09:00~15:30에는 새 연간 조회를 불완전 상태로 반환하고 15:30 이후 재시도를 안내한다. 일부 기간만 받아 연간 합계로 표시하지 않는다.
- 일반 기간은 최대 12회/15초, 1년은 최대 48회/45초의 계좌 조회 GET 예산을 사용한다. 인증 재시도 GET도 횟수에 포함한다. GET 사이 기본 간격은 1초다.
- 한 구간 최대 10페이지, 검증된 주문 최대 5,000건이다. 제한에 걸리거나 종료 헤더·연속 조회 키가 없거나 키가 반복되면 `incomplete`다. 처음 몇 페이지만 가져와 `success`로 표시하지 않는다.
- 실제 LIVE 계좌의 1년 조회는 각각 **13회 GET**으로 전 구간 조회를 완료했다.
- 성공한 전체 결과에서 중복 제거·정렬·합계를 계산한 뒤 UI 페이지를 자른다. 기본 20건, 최대 100건이며 `next_offset`으로 더 본다. 다음 페이지는 첫 응답의 `end_at`을 `as_of`로 전달한다.
- 성공한 정규화 결과만 최대 64개, 120초 동안 다음 페이지용으로 보관한다. 키는 역할·사용자·계좌·상품·환경·자격증명 변경을 반영한 해시다. 첫 조회와 새로고침은 실제 KIS를 다시 읽는다. 다른 사용자나 자격증명으로 이전 스냅샷을 꺼낼 수 없다.

양수 체결 수량과 요청 수량, 방향, 종목, 날짜 및 잔량을 검증한다. 체결 0건은 제외하고 부분 체결은 확인된 수량만 반영한다. 같은 거래일·채번지점·주문번호의 누적 체결 응답은 더하지 않고 최대 검증 수량 한 항목으로 취급한다. 건수는 이 체결 주문 수다.

평균가와 금액이 없으면 임의 값이나 주문 가격을 쓰지 않는다. KIS가 금액을 제공하면 그 값을 쓰고, 없으면 확인된 수량과 평균가로 체결 총액을 계산한다. 확인되지 않은 금액이 포함된 방향의 합계는 `null`/`미확인`이다. 수수료·실현손익은 계산하지 않는다. `ord_tmd`를 체결 시각으로 사용하지 않는다.

응답은 `source=kis_broker_executions`와 성공·완전성을 명시한다. 오류·인증 실패·계좌 미연결·불완전 조회에서는 **count와 합계가 null이며 items는 비어 있다**. 정상 0건과 구별한다. 원본 브로커 응답, 계좌번호 및 인증 정보는 반환하지 않는다. HTTP 응답은 `no-store, private`다.

## 홈 카드 가독성

기존 운영 모드 압축, 자산 5개 지표 정렬, 보유 주식 펼치기와 AI 결과 배치는 유지한다.

거래 내역 제목은 18px/w800, 건수는 20px/w900, 매수·매도 합계는 18px/w800, 실제 거래 행은 16px/w700으로 표시한다. 매수는 기존 다크 테마의 붉은색, 매도는 푸른색 강조 토큰을 사용한다. 손익 색상 등 다른 화면의 색상 정책은 바꾸지 않는다.

기본은 접힘이며 최근 **1건**만 표시한다. 정상 0건은 제목과 `오늘 체결 0건`으로 작게 표시하고, 펼쳤을 때 `선택한 기간에 실제 체결 내역이 없습니다.`를 안내한다. 기간 버튼은 선택 배경과 굵은 글씨로 구분한다. 금액은 보조 회색 설명으로 작게 숨기지 않는다.

조회 중, 계좌 미연결, 인증 실패, 조회 실패와 불완전 상태는 각각 요청된 문구로 표시한다. 새로고침 버튼과 Pull-to-refresh를 제공한다. 기간·브로커·로그인 변경 시 오래된 응답을 버리고 이전 내역을 즉시 비운다. 거래 내역 오류가 자산·보유 주식·AI 카드 표시를 막지 않는다.

## 검증 결과

- 새 KIS 계좌 조회 회귀: **35개 통과**. 격리 DB, FakeBrokerHTTP와 Fake 토큰 관리자만 사용했다.
- 신규/기존 체결 조회 관련 **75개가 전체 회귀에서도 통과**했다.
- 스케줄러·전체 생명주기·PR142 동기화 리플레이: **114개 통과, 선택적 운영 백업 테스트 1개 건너뜀**.
- Flutter 홈·계좌 경로·오류·가독성 회귀: **22개 통과**.
- 전체 Flutter: **805개 통과**.
- Flutter analyze: **이슈 없음**.
- 전체 백엔드 pytest: **2,912개 통과, 1개 건너뜀**, 종료 코드 0. 총 2,913개 수집, 2,932.39초(48분 52초). 건너뛴 항목은 `AUTO_INVEST_DIAGNOSTIC_CLONE`을 지정해야 하는 기존의 선택적 운영 백업 리플레이다. 필수 스케줄러·생명주기 및 새 계좌 체결 조회 테스트는 모두 통과했다. 기존 deprecation·중복 OpenAPI Operation ID 경고 12개는 그대로다.
- `python -m compileall app`, `git diff --check`: **통과**.

최종 로그는 `.tmp/pr143-followup-replay.log`, `.tmp/pr143-followup-flutter-full.log`, `.tmp/pr143-followup-backend-full.log`에 있다. 기존 테스트의 외부 KIS HTTP 차단 정책을 유지했으며 실제 조회는 테스트 밖의 별도 읽기 전용 검증으로만 수행했다.

전체 백엔드 실행은 `python -u -m pytest app/tests -q -vv -o faulthandler_timeout=90 -p no:cacheprovider`로 수행했다. 지연 구간 확인용 출력과 진단을 추가하고 캐시 쓰기만 비활성화했으며 테스트를 제외하지 않았다.

검토용 이미지는 Fake 데이터로 생성했다: [접힌 홈 화면](../.tmp/pr143-followup-home-after.png), [펼친 거래 내역](../.tmp/pr143-followup-history-expanded.png), [모바일](../.tmp/pr143-followup-mobile.png). 원본 계좌 정보는 포함하지 않는다.

## 이번 후속 수정 파일

| 파일 | 역할 |
| --- | --- |
| `app/brokers/kis_account_execution_reader.py` | 공식 계좌 체결 GET·헤더·재시도·호출 예산 |
| `app/brokers/kis_client.py` | 관리자 전용 새 계좌 조회 함수 추가 |
| `app/services/user_broker_account_service.py` | 사용자 조회 전용 클라이언트에 새 조회 함수 추가 |
| `app/services/kis_account_execution_history_service.py` | 기간 분할·검증·완전성·중복·합계·스냅샷 |
| `app/routes/kis_account_executions.py` | 관리자/일반 사용자 인증 API |
| `app/main.py` | 새 라우터 등록 |
| `app/tests/integration/test_kis_account_execution_history.py` | Fake 기반 계정·환경·페이지·오류·기간 회귀 |
| `lib/core/network/api_client.dart` | KIS 계정별 새 GET 경로 |
| `lib/features/dashboard/dashboard_controller.dart` | 상태 구분과 이전 응답 제거 |
| `lib/features/home/widgets/trade_history_card.dart` | 굵은 제목·숫자·체결 행, 기간 대비, 새로고침 |
| `lib/models/trade_fill_history.dart` | 새 스키마와 불완전 응답 검증 |
| `test/home_compact_trade_history_test.dart` | 신규 경로·가독성·오류 구분 회귀 |
| `docs/pr143-home-compact-trade-history.md` | 최초 보고서에 후속 대체 사실 표시 |
| `docs/pr143-kis-broker-executions-followup.md` | 원인·조회 구조·실계좌 검증·최종 보고 |

자동매매 스케줄·주문 제출/취소·점수·리스크·사이징·포지션 관리·TP/SL·Kill Switch·실거래 권한은 변경하지 않았다. PR142의 동기화 코드와 원본 주문 상태도 변경하지 않았다. `.metadata`, `config/watchlist_kr.yaml`, `daily_ops_readonly.py` 및 기존 사용자 문서들은 보존한다.
