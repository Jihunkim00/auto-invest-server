# PR141 — 스냅샷 오류 기록과 제한된 자동 복구

## 229번에서 확인한 사실과 확인할 수 없는 원인

운영 코드를 수정하기 전에 원본 DB를 읽기 전용으로 확인했다. 2026-10-28 스냅샷 229는 KST 12:50:07에 시작해 12:53:37에 `failed`로 종료했다. `source_count=200`, `scored_count=200`, `error_count=1`이고 종목 행은 200개다. 마지막 정상 스냅샷 228은 11:53:22에 완료했으며, 다음 정상 스냅샷 230은 13:53:29에 완료했다. 관리자 13:30과 test01 13:45는 최신 스냅샷의 실패로 차단됐다.

229에는 종목별 quote/daily/indicator 예외 기록이 없다. 실패 종목, HTTP 상태, 인증·네트워크·호출 제한 여부는 확인 불가다. 종가로 가격을 보완하면서 quote 오류가 남는 기존 코드 경로는 이 집계와 양립하지만, 실제 원인이라는 증거는 없다. 새 테스트의 TimeoutError는 **명시적으로 주입한 가상 오류**이며 229의 원인을 복원한 결과가 아니다.

PR140 보고서와 기존 16개 테스트는 당시의 기록과 기능을 검증하는 기준선이다. 상세 오류·복구 메타데이터가 없는 과거 229를 일시 오류로 재분류하거나 성공으로 덮어쓰지 않는다. 이 경우에는 자동 복구 대상을 추정하지 않고 기존 안전 차단을 유지한다. 새 코드에서 원인이 분류된 일시 오류에 자동 복구를 적용한다. 인증 거부·불충분한 지표·원인 미분류 오류는 자동 재시도를 중단한다.

## 변경 동작

`WatchlistSnapshotService._build_item`은 quote, daily, indicator, exception 단계를 구분한다. 오류 기록은 종목 코드, 단계, 고정된 원인 코드, 허용된 예외 유형, HTTP 상태, 재시도 여부·회차, 해결 여부, UTC 시각만 저장한다. 원본 예외 문자열, URL, 응답 본문, 계좌번호, 토큰은 새 오류 테이블·로그·오류 API에 기록하지 않는다. 외부 어댑터가 오류 딕셔너리를 제공해도 허용된 필드와 값만 받아들인다.

`MarketDataSnapshotService`는 예외가 문자열로 바뀌기 전에 안전한 분류를 제공한다. 기존 소비자와의 호환성을 위한 인메모리 오류 문자열은 유지하지만 스냅샷 오류 기록에는 사용하지 않는다. 지표 계산과 Quant 산식은 기존 서비스를 그대로 사용한다.

`SnapshotRecoveryCoordinator`가 다음 정책을 담당한다. 정책 상수는 `app/services/watchlist_snapshot_policy.py`에 있다.

| 제한 | 값 |
|---|---|
| 종목별 시도 | 최초 1회 + 추가 2회, 대기 2초·5초 |
| 전체 실패 후 복구 | 새 스냅샷 최대 3회, 대기 15초·45초·120초 |
| 복구 체인의 시간 | 최초 스냅샷 시작부터 900초 |
| 스냅샷 한 번의 작업 시간 | 480초, UTC·monotonic 두 시계로 확인 |
| 최초 작업의 물리적 READ 호출 | 최대 600회 |
| 후속 복구 전체의 물리적 READ 호출 | 합계 최대 60회 |
| READ 최소 간격 | 1초, 기존 KIS 제한도 유지 |
| 정상 종목 재사용 | 같은 universe·gate, 정상 지표·가격·점수, 개별 captured_at 기준 900초 이내 |
| DB 실행 점유 | KR별 하나, 600초 lease와 소유 토큰으로 늦은 작업 차단 |

최초 실패 이후에도 정상 199종목을 재분석하지 않는다. 부분 결과를 종목 처리마다 저장하고, 후속 스냅샷은 정상 행을 원래 `captured_at` 그대로 복사해 오류·미완료 종목만 다시 조회한다. 오래됐거나 유효하지 않은 행은 다시 조회한다. 복구가 성공하려면 새 조회 결과와 재사용한 정상 데이터 전체가 검증되고, 200종목이 모두 산출되며, 미해결 오류가 없어야 한다. 실패 스냅샷과 그 오류 기록은 그대로 남는다. 개별 재시도로 해결한 오류는 해당 실행에서 `resolved=true`로 보관한다.

KIS 실제 READ 전송 경계에서 호출 예산을 차감·커밋한 뒤 요청한다. 토큰 만료에 따른 READ 재전송도 같은 예산과 간격을 적용한다. 예산 수치는 시장 데이터 READ 요청의 보수적 상한이며 실제 전송 전에 중단되면 더 크게 계산될 수 있다. 기존 인증 토큰 발급 제한과 다른 계정의 KIS 클라이언트 제한도 유지한다. 새 복구 경로는 주문·취소·정정 API를 호출하지 않는다.

`WatchlistSnapshotScheduler._run`은 정규 시간 사이에도 15초마다 복구를 확인한다. `_bootstrap_if_needed`는 오래되지 않은 이전 성공이 있더라도 최신 실패의 복구를 먼저 확인한다. 같은 날 실패 후 재시작으로 횟수·예산을 초기화하지 않는다. 최신 실행이 성공한 경우에는 기존의 2시간 경과 bootstrap 갱신을 유지한다. 다음 정규 갱신은 새 체인을 만들고 이전 복구 체인을 superseded로 표시한다. 같은 분의 bootstrap·정규 갱신 중복도 피한다. stop 후에도 응답을 기다리는 스레드가 살아 있으면 참조와 취소 상태를 유지하여 중복 스레드 시작을 막는다.

실행 중 프로세스가 종료되면 DB lease가 만료된 후 새 프로세스가 저장된 부분 결과와 남은 예산으로 복구한다. 만료 전에는 재진입하지 않는다. 완료·종목 저장·호출 예산 변경에 소유권 검사를 적용해 이전 작업의 늦은 응답이 성공 상태를 게시하거나 새 작업의 점유를 지울 수 없게 한다. 취소와 시간 초과는 실패로 기록한다. 복구 시간·횟수·호출 예산 중 하나가 소진되면 종료한다. HTTP 한 번의 기존 10초 timeout은 유지되므로 이미 전송된 요청을 강제로 끊지는 않으며, 돌아온 뒤 새 READ와 성공 게시를 차단한다.

새 DB 테이블은 `watchlist_snapshot_errors`, `watchlist_snapshot_recoveries`, `watchlist_snapshot_refresh_claims`다. 기존 `init_db()`의 additive metadata 생성으로 새 테이블을 생성할 수 있다. **이번 작업에서 원본 DB에 init_db나 스키마 변경을 실행하지 않았다.** 테스트 DB와 운영 백업의 독립 복사본에만 생성했다.

상태 조회 `/market-analysis/watchlist/snapshot/status`에 복구 상태·횟수·호출량·마감 시각을 추가했다. `/market-analysis/watchlist/snapshot/{run_id}/errors`는 안전한 종목별 오류 정보를 제공한다. 갱신 API 오류 응답도 원본 예외 문자열을 노출하지 않는다.

## 네 가지 결과의 구분

| 시나리오 | 검증 입력과 결과 |
|---|---|
| 오류 → 정상 복구 → 슬롯 분석 | 실제 10/28 설정을 복사한 격리 DB + 합성 시세·일봉. 12:50:08에 시작한 200종목 갱신 중 한 종목 quote가 3회 실패한다. 199종목을 재사용하고 오류 종목만 한 번 더 조회해 약 12:57:09에 새 정상 스냅샷을 확보한다. 관리자 13:30과 test01 13:45가 실제 Dispatcher를 거쳐 각각 분석에 진입한다. 과거 229와 새 실패 실행은 계속 failed다. |
| 오류 → 복구 실패 → 안전 차단 | 같은 조건에서 오류가 지속되면 후속 3회가 모두 실패한다. 두 슬롯은 기존 `watchlist_snapshot_not_ready`로 차단되고 분석·FakeBroker 제출은 0회다. |
| 스냅샷 성공 → 점수 미달 → HOLD | 별도의 합성 OHLCV 통합 테스트. 실제 C 산출은 65 이상이지만 가상 GPT 점수 59로 기존 GPT60 게이트를 통과하지 못한다. ENTRY_DECISION은 hold이고, 기존 슬롯 원장의 상태는 blocked / `gpt_buy_score_below_threshold`다. 제출·주문 생성은 0회다. |
| 스냅샷 성공 → 점수·리스크 통과 → FakeBroker | 같은 합성 OHLCV에서 가상 GPT 점수 70을 사용한다. 실제 C65/GPT60/Final65, 실제 리스크·주문 검증을 통과한 경우 FakeBroker 1회, FILLED 기록을 확인한다. 실제 KIS 제출은 0회다. |

원본에는 13:30/13:45의 C/GPT 입력·결과가 없으므로 첫 번째 시나리오는 분석 진입만 입증한다. 그 시간의 실제 매수 결정을 복원했다고 주장하지 않는다. 뒤의 두 시나리오는 합성 데이터와 GPT 응답을 명시한 별도 테스트로 검증한다.

admin/test01의 실제 프로필 5/8, 소유자 1/2, 시간표, 예산, 거래 상한을 격리 복사본에서 유지했다. test01의 기존 미해결 주문 1건도 보존했다. 프로필별 분석 스냅샷과 슬롯은 별도로 기록되고, 공유 raw 스냅샷 복구는 계정별 주문 상태를 변경하지 않는다. 기존 PR140 병렬 계정 테스트도 회귀 대상이다.

C65/GPT60/Final65, Quant·GPT 판단 코드, sizing, TP/SL, 현금 전용, 최대 포지션, 거래 횟수, 주문 가능 조회의 10초 신선도, 중복·예약·idempotency, 시장 시간·마감·실행 권한, 매수 600초·작업 720초 정책은 변경하지 않았다. 최신 스냅샷이 성공하지 못하면 기존 실행 게이트가 매수를 차단한다.

## 검증

새 테스트: `app/tests/test_watchlist_snapshot_recovery.py`, `app/tests/integration/test_pr141_snapshot_recovery_replay.py`, `app/tests/integration/test_pr141_recovery_full_pipeline.py`.

최종 수정본 기준 결과는 다음과 같다. 필수 replay와 PR140 재현은 전체 백엔드 실행에도 포함됐다.

| 검증 | 결과 |
|---|---:|
| 전체 백엔드 pytest | **2,781 passed**, 61 warnings, 839.18초 |
| `test_kis_automation_scheduler_replay.py` | **39 passed** |
| `test_kis_automation_full_lifecycle_replay.py` | **19 passed** |
| PR140 10/28 운영 재현 | **16 passed** |
| 새 복구 단위 테스트 | **26 passed** |
| 새 10/28 계정·슬롯 복구 통합 테스트 | **2 passed** |
| 새 합성 OHLCV 전체 파이프라인 | **2 passed** |
| `flutter --no-version-check analyze` | **No issues found** |
| `flutter --no-version-check test --reporter compact` | **783 passed** |
| `python -m compileall -q app` | **PASS** |
| `git diff --check`, 신규 파일 공백 검사 | **PASS** |

백엔드는 테스트 전용 pytest-xdist 환경으로 `python -m pytest app/tests -q -p no:cacheprovider -n 8 --dist worksteal --maxfail=1 --tb=short --junitxml=.tmp/pr141-snapshot-recovery/backend-final.xml`을 실행했다. JUnit 결과에서 위 파일별 건수와 실패·오류 0건을 다시 확인했다. 일반 직렬 실행에도 테스트 코드 변경은 필요 없다. warnings는 기존 FastAPI/websockets/SQLite deprecation과 기존 OpenAPI operation ID 중복이다.

로컬 검증 산출물은 `.tmp/pr141-snapshot-recovery/backend-final.xml`, `validation.json`, `original-integrity.json`이다. 운영 복사본 시나리오별 공개 결과와 주요 14개 테이블 무결성 비교는 `.tmp/pr140-production-replay/`에도 저장된다. 복구 성공·실패 양쪽 모두 외부 HTTP, 실제 KIS 제출, 실제 Alpaca 제출 카운터가 0이다.

원본 DB SHA-256 기준값: `0cbfda0d1bf5a54ca7b868bd2517860690fda4dc7bc5e9d95638edbcf01fc521`. 운영 재현 fixture는 실행 전후 원본 전체 파일 해시와 주요 14개 테이블의 행 수·내용 해시를 비교한다. 테스트 입력의 원본 OHLCV 부재와 역사적 C 재계산 불가는 PR140과 동일하게 유지한다. 실제 KIS/Alpaca 주문·원본 DB 변경·커밋·푸시·PR 생성은 수행하지 않는다.
