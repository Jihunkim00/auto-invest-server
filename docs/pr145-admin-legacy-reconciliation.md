# PR145 — 관리자 legacy 주문 복구와 장전 사전점검

## #18 복구 가능성

현재 운영 DB의 #18은 그대로 `REQUESTED`이며, 운영 DB를 변경하지 않았다. 읽기 전용 검토안은 실제 관리자 KIS 계정의 현재 선택 프로필과 계좌 범위가 일치하고, 아래 브로커 증거가 모두 확인되어 생성됐다.

- 주문 #18: owner `NULL`, 정책 사용자 ID `1`, KIS 실계좌, `036460` 매수 7주, 생성 2026-10-28.
- 현재 선택 프로필: ID 5, owner 1, KIS/KR, 활성.
- KIS 2026-10-28 전체 주문 조회: `CCLD_DVSN=00`, 거래소 `ALL`, 페이지 1/1 완료, 전체 0건, `036460` 0건.
- 별도 현재 미체결 주문 조회 성공: 0건. 현재 보유 조회 성공: 0종목.
- 계좌 매수 실행 claim 0건. 연결 reservation #10은 `reserved`.
- 검증 로그 #15는 `validated_for_submission=true`; 주문 ID가 연결된 TradeRunLog는 0건이다. 같은 시각의 분석 #261은 `LIVE_READY`, `submission_eligible=true`지만 분석 단계이고 주문 ID가 없다. scheduler slot #40은 attempt 1에서 `account_snapshot_retry_pending_1_of_3` / `failure_stage=account_snapshot`이며 바깥 슬롯은 최종 timeout이다. 이 기록만으로 뒤의 재시도에서 HTTP 호출이 없었다고 증명할 수 없으므로, 과거 호출 여부 자체를 `not_submitted`로 단정하지 않는다.

별도 종결 상태 `LEGACY_ABSENCE_VERIFIED`는 **완전한 KIS 이력에 브로커 주문 기록이 없음**을 뜻한다. `CANCELED`, `not_submitted`, 실제 submit 미호출을 뜻하지 않는다. 독립된 계좌 이력·현재 상태 증거와 관리자의 명시적 승인 없이 이 상태를 사용할 수 없다. 원본 요청/응답은 보존하고, #18 원본 fingerprint, #10 reservation fingerprint, 승인자, 승인 참조, 브로커 증거 요약, 변경 전후 상태를 감사 테이블과 TradeRunLog에 기록한다.

## 적용 절차

1. 변경 코드를 배포한 뒤 애플리케이션을 시작해 `init_db()`가 `kis_legacy_order_reconciliations` 테이블을 생성했는지 확인한다. 테이블이 없으면 적용은 `legacy_reconciliation_schema_missing`으로 거부된다.
2. 관리자 승인 직전에 읽기 전용 검토안을 다시 생성한다.

   ```powershell
   .\.venv\Scripts\python.exe scripts/reconcile_admin_legacy_kis_order.py --output .tmp/pr145-legacy-order18-review.json
   ```

3. 출력의 주문/프로필/계좌, 전체 이력 범위, 현재 미체결/보유 상태, 실행 흔적, digest를 관리자가 확인한다. `complete=false`, 동일 종목 이력/현재 미체결/보유, KIS 읽기 실패, fingerprint 변경, claim 존재, 계정 범위 변경이면 승인안이 생성되지 않거나 적용 시 거부된다.
4. 관리자가 승인한 경우에만 검토 파일의 digest와 변경 승인 참조를 전달해 적용한다. 적용은 KIS GET을 다시 실행하고 계좌 claim mutex 아래에서 계획·fingerprint·reservation을 재검증한다.

   ```powershell
   .\.venv\Scripts\python.exe scripts/reconcile_admin_legacy_kis_order.py --apply-plan .tmp/pr145-legacy-order18-review.json --approve-digest <관리자가_확인한_digest> --approval-reference <승인_티켓>
   ```

이 적용 명령은 로컬 DB 상태만 고친다. KIS 매수·매도·취소 호출은 포함하지 않는다. 이 작업에서는 적용 명령을 실행하지 않았다.

## 한도와 사전점검

운영 DB 복제본을 메모리로 복사해 FakeBroker로 실행했다. 승인 전 `(filled=0, unresolved=1, remaining=0)`, 금액 예약 `258,300원`; 승인 후 `(0, 0, 1)`, 금액 예약 `0원`이었다. reservation #10은 `reserved → blocked`, #13과 #19 fingerprint는 유지됐다. 운영 DB 파일 hash도 복제 실행 전후 동일했다.

실제 2026-11-09 21:55 KST preflight는 2026-11-10 대상으로 `BLOCKED`였다. scheduler health는 healthy, LIVE 계정 인증/현재 positions·open orders 조회는 신뢰 가능(각 0), active exit retry와 account buy claim은 0이었지만, #18 때문에 `unresolved_entries=1`, `remaining_entry_capacity=0`이었다. 미래 계좌 상태는 아직 관측되지 않았다고 함께 표시했다.

FakeBroker를 사용한 2026-11-10 08:40 preflight 시나리오는 승인 전 `unresolved_entry_limit_hit`으로 `BLOCKED`, 복제본에서 승인 복구 후에는 한도와 계좌 스냅샷이 정상인 상태에서 `READY`였다. 실제 11월 10일 08:40의 READY는 그 시점에 다시 실행한 preflight와 실제 scheduler/KIS 상태에 달려 있으며, 이 결과는 미래 운영 상태를 보증하지 않는다. AI 점수는 예정 분석 전까지 평가되지 않으며, READY도 주문 실행을 보장하지 않는다.

```powershell
.\.venv\Scripts\python.exe scripts/check_admin_preflight.py --date 2026-11-10
```

현재 운영 검토 파일은 `.tmp/pr145-legacy-order18-review.json`, 복제 검증은 `.tmp/pr145-operating-clone-verification.json`, 08:40 실제 운영 전 상태 진단은 `.tmp/pr145-preflight-nov10.json`에 있다. 이 파일들에는 계좌번호나 인증정보를 기록하지 않았다.

## 검증

- 신규 legacy/preflight 및 PR144 reconciliation 테스트: **43 passed**.
- 필수 scheduler replay, full lifecycle replay, PR144 scheduler diagnostics: **72 passed**.
- 전체 backend pytest: **2,969 passed, 1 skipped**. Skip은 별도 `AUTO_INVEST_DIAGNOSTIC_CLONE` 운영 백업이 없는 선택형 과거 데이터 테스트다.
- `python -m compileall app`: 통과. `git diff --check`: 통과.
- 복제 검증은 FakeBroker만 사용했고 실제 KIS mutation 0회. KIS 계정 검토와 preflight는 읽기 GET만 수행했고 원본 DB file hash가 동일했다.
