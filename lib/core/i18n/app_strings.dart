import 'app_language.dart';

class AppStrings {
  const AppStrings(this.appLanguage);

  final AppLanguage appLanguage;

  bool get isKorean => appLanguage == AppLanguage.korean;

  String get appTitle => 'AUTO INVEST';
  String get home => isKorean ? '홈' : 'Home';
  String get watchlist => isKorean ? '관심종목' : 'Watchlist';
  String get analysis => isKorean ? '분석' : 'Analysis';
  String get trading => isKorean ? '거래' : 'Trading';
  String get logs => isKorean ? '기록' : 'Logs';
  String get settings => isKorean ? '설정' : 'Settings';
  String get kisAutomation => isKorean ? '한국투자증권 자동화' : 'KIS Automation';

  String get language => isKorean ? '언어' : 'Language';
  String get appLanguageLabel => isKorean ? '앱 언어' : 'App language';
  String get korean => '한국어';
  String get english => 'English';
  String get languageDescription => isKorean
      ? '화면 표시와 Agent Chat 요청 언어에 즉시 적용됩니다.'
      : 'Applies immediately to UI labels and Agent Chat requests.';
  String get languagePersistenceNote => isKorean
      ? '현재 선택은 실행 중인 앱에 적용됩니다.'
      : 'The current selection applies to this running app session.';

  String get kisBroker => isKorean ? '한국투자증권' : 'KIS';
  String get alpacaBroker => isKorean ? '알파카' : 'Alpaca';
  String get kisBrokerCompact => isKorean ? '한국투자' : 'KIS';
  String get alpacaBrokerCompact => alpacaBroker;
  String get kisBrokerMarket => isKorean ? '한국투자증권 / 국내' : 'KIS / KR';
  String get alpacaBrokerMarket => isKorean ? '알파카 / 미국' : 'Alpaca / US';
  String get settingsKisSubtitle => isKorean
      ? '한국투자증권 안전 상태와 수동 실거래 상태입니다.'
      : 'KIS safety and manual live status.';
  String get settingsAlpacaSubtitle => isKorean
      ? '알파카 모의 계좌와 공통 안전 상태입니다.'
      : 'Alpaca paper and common safety status.';
  String get homeKisSubtitle => isKorean
      ? '한국투자증권 계좌, 수동 실거래 안전 상태, 최근 국내 활동입니다.'
      : 'KIS account, manual live safety, and recent KR activity.';
  String get homeAlpacaSubtitle => isKorean
      ? '알파카 모의 포트폴리오, 관심종목 상태, 최근 미국 활동입니다.'
      : 'Alpaca paper portfolio, watchlist status, and recent US activity.';
  String get logsKisSubtitle => isKorean
      ? '한국투자증권 / 국내 활동을 먼저 표시합니다.'
      : 'Showing KIS / KR activity first.';
  String get logsAlpacaSubtitle => isKorean
      ? '알파카 / 미국 활동을 먼저 표시합니다.'
      : 'Showing Alpaca / US activity first.';

  String get refresh => isKorean ? '새로고침' : 'Refresh';
  String get cancel => isKorean ? '취소' : 'Cancel';
  String get confirm => isKorean ? '확인' : 'Confirm';
  String get yes => isKorean ? '예' : 'YES';
  String get no => isKorean ? '아니오' : 'NO';
  String get ready => isKorean ? '준비됨' : 'READY';
  String get blocked => isKorean ? '차단됨' : 'BLOCKED';
  String get enabled => isKorean ? '활성' : 'ENABLED';
  String get disabled => isKorean ? '비활성' : 'DISABLED';
  String get none => isKorean ? '없음' : 'none';
  String get status => isKorean ? '상태' : 'Status';
  String get statusNotLoaded =>
      isKorean ? '상태를 아직 불러오지 않았습니다' : 'Status not loaded';
  String get safeMode => isKorean ? '안전 모드' : 'SAFE MODE';
  String get gptBacked => isKorean ? 'GPT 기반' : 'GPT-BACKED';
  String get fallbackRouter => isKorean ? '대체 라우터' : 'FALLBACK ROUTER';
  String get fallbackParser => isKorean ? '대체 파서' : 'FALLBACK PARSER';
  String get serverSideApi => isKorean ? '서버 API' : 'SERVER-SIDE API';
  String get confirmRequired => isKorean ? '확인 필요' : 'CONFIRM REQUIRED';
  String get noAutoSubmit => isKorean ? '자동 제출 없음' : 'NO AUTO SUBMIT';
  String get liveOrder => isKorean ? '실주문' : 'LIVE ORDER';
  String get validationRequired => isKorean ? '검증 필요' : 'VALIDATION REQUIRED';
  String get riskGated => isKorean ? '위험 게이트 적용' : 'RISK GATED';
  String get profileOnly => isKorean ? '프로필 전용' : 'PROFILE ONLY';
  String get noOrderSubmit => isKorean ? '주문 제출 없음' : 'NO ORDER SUBMIT';
  String get strategyTarget => isKorean ? '전략 목표' : 'STRATEGY TARGET';
  String get noOrder => isKorean ? '주문 없음' : 'NO ORDER';
  String get readOnly => isKorean ? '읽기 전용' : 'READ ONLY';
  String get safeAnalysis => isKorean ? '안전 분석' : 'SAFE ANALYSIS';
  String get noValidation => isKorean ? '검증 없음' : 'NO VALIDATION';
  String get noSettingsChange => isKorean ? '설정 변경 없음' : 'NO SETTINGS CHANGE';
  String get prefillOnly => isKorean ? '입력값 준비 전용' : 'PREFILL ONLY';
  String get manualReviewOnly => isKorean ? '수동 검토 전용' : 'MANUAL REVIEW ONLY';
  String get manualValidationRequired =>
      isKorean ? '수동 검증 필요' : 'MANUAL VALIDATION REQUIRED';
  String get confirmLiveManual =>
      isKorean ? '수동 실거래 확인' : 'CONFIRM_LIVE MANUAL';
  String get authRequired => isKorean ? '인증 필요' : 'AUTH REQUIRED';

  String get agentAssistant => isKorean ? 'Agent Assistant' : 'Agent Assistant';
  String get agentAssistantSubtitle => isKorean
      ? '분석, 포트폴리오, 확인이 필요한 한국투자증권 주문 준비를 요청하세요.'
      : 'Ask for analysis, portfolio, or confirmed KIS order prep.';
  String get agentNaturalLanguageReview =>
      isKorean ? '자연어 명령 검토' : 'Natural language command review';
  String conversationLabel(String key) =>
      isKorean ? '대화 $key' : 'Conversation $key';
  String get newChat => isKorean ? '새 대화' : 'New Chat';
  String get refreshHistory => isKorean ? '기록 새로고침' : 'Refresh History';
  String get expandAgentChat =>
      isKorean ? 'Agent Chat 펼치기' : 'Expand Agent Chat';
  String get collapseAgentChat =>
      isKorean ? 'Agent Chat 접기' : 'Collapse Agent Chat';
  String get resizeAgentChat =>
      isKorean ? 'Agent Chat 크기 변경' : 'Resize Agent Chat';
  String get openFullAgentChat =>
      isKorean ? '전체 Agent Chat 열기' : 'Open Full Agent Chat';
  String get loadingPreviousChat =>
      isKorean ? '이전 대화를 불러오는 중...' : 'Loading previous chat...';
  String get askAgentHint =>
      isKorean ? 'Agent Assistant에게 물어보세요...' : 'Ask Agent Assistant...';
  String get messageAgentHint =>
      isKorean ? 'Agent Assistant에게 메시지 보내기...' : 'Message Agent Assistant...';
  String get send => isKorean ? '보내기' : 'Send';
  String get archive => isKorean ? '보관' : 'Archive';
  String get minimize => isKorean ? '최소화' : 'Minimize';
  String get close => isKorean ? '닫기' : 'Close';
  String get agentSafetyIntro => isKorean
      ? 'Agent Chat은 명시적인 확인 카드가 있어야만 한국투자증권 실주문을 제출할 수 있습니다. 제출 전 서버 검증과 위험 게이트를 다시 실행합니다.'
      : 'Agent Chat can only submit live KIS orders after an explicit confirmation card. Backend validation and risk gates rerun before submit.';
  String get agentSafetyNotice => isKorean
      ? 'Agent Chat의 한국투자증권 실주문은 명시적인 확인 카드가 필요합니다. 제출 전 서버 검증과 위험 게이트를 다시 실행하며 OpenAI API 호출은 FastAPI 서버에서만 수행됩니다.'
      : 'Live KIS orders from Agent Chat require an explicit confirmation card. Backend validation and risk gates rerun before submit. OpenAI API is called only from the FastAPI server.';
  String get agentEnterMessage => isKorean
      ? 'Agent Assistant에 보낼 메시지를 입력하세요.'
      : 'Enter a message for Agent Assistant.';
  String get agentParsing => isKorean
      ? 'FastAPI Agent 엔드포인트로 분석 중...'
      : 'Parsing with the FastAPI agent endpoint...';
  String get agentAnsweredNoOrder => isKorean
      ? 'Agent Chat이 응답했습니다. 주문은 제출되지 않았습니다.'
      : 'Agent chat answered. No order submitted.';
  String get agentErrorNoOrder => isKorean
      ? 'Agent Chat 오류가 발생했습니다. 주문은 제출되지 않았습니다.'
      : 'Agent chat returned an error. No order submitted.';
  String get chatEndpointFallback => isKorean
      ? '채팅 엔드포인트를 사용할 수 없어 명령 검토로 전환합니다...'
      : 'Chat endpoint unavailable. Falling back to command review...';

  String get autoBuyOperations => isKorean ? '자동매수 운영' : 'Auto Buy Operations';
  String get autoBuyScheduler => isKorean ? '자동매수 스케줄러' : 'Auto Buy Scheduler';
  String get autoBuyPromotionQueue =>
      isKorean ? '자동매수 프로모션 검토 목록' : 'Auto Buy Promotion Queue';
  String get autoBuyPhase1 => isKorean ? '자동매수 1단계' : 'Auto Buy Phase 1';
  String get autoSellPhase1 => isKorean ? '자동매도 1단계' : 'Auto Sell Phase 1';
  String get portfolioOrchestrator =>
      isKorean ? '포트폴리오 자동 운영' : 'Portfolio Orchestrator';
  String get unifiedAutomationLoop =>
      isKorean ? '통합 자동화 루프' : 'Unified Automation Loop';
  String get checkPositionsFirst =>
      isKorean ? '보유 종목 점검 먼저' : 'Check Positions First';
  String get autoSellFirst => isKorean ? '자동매도 우선' : 'Auto Sell First';
  String get autoBuySecond => isKorean ? '자동매수 후순위' : 'Auto Buy Second';
  String get dailyActionLimit =>
      isKorean ? '하루 최대 실행 제한' : 'Daily Action Limit';
  String get blockedWhenSyncRequired =>
      isKorean ? '동기화 필요 시 차단' : 'Blocked When Sync Required';
  String get runResult => isKorean ? '실행 결과' : 'Run Result';
  String get actionTaken => isKorean ? '실행된 동작' : 'Action Taken';
  String get sellSubmitted => isKorean ? '매도 실행됨' : 'Sell Submitted';
  String get buySubmitted => isKorean ? '매수 실행됨' : 'Buy Submitted';
  String get noActionTaken => isKorean ? '실행 없음' : 'No Action';
  String get refreshPortfolioOrchestratorStatus =>
      isKorean ? '포트폴리오 자동 운영 상태 새로고침' : 'Refresh Orchestrator Status';
  String get runPortfolioOrchestratorOnce =>
      isKorean ? '포트폴리오 자동 운영 1회 실행' : 'Run Orchestrator Once';
  String get expandOrchestratorDetails =>
      isKorean ? '상세 펼치기' : 'Expand Details';
  String get collapseOrchestratorDetails =>
      isKorean ? '상세 접기' : 'Collapse Details';
  String get latestPositionManagementResult =>
      isKorean ? '최근 포지션 관리 결과' : 'Latest Position Management Result';
  String get orchestratorAutoSellResult =>
      isKorean ? '자동매도 결과' : 'Auto Sell Result';
  String get orchestratorAutoBuyResult =>
      isKorean ? '자동매수 결과' : 'Auto Buy Result';
  String get skippedBuyReason =>
      isKorean ? '자동매수 건너뜀 사유' : 'Buy Skipped Reason';
  String get skippedSellReason =>
      isKorean ? '자동매도 건너뜀 사유' : 'Sell Skipped Reason';
  String get pendingOrderConflicts =>
      isKorean ? '대기 주문 충돌' : 'Pending Order Conflicts';
  String get syncRequiredCount =>
      isKorean ? '동기화 필요 건수' : 'Sync Required Count';
  String get criticalExitCandidateCount =>
      isKorean ? '중요 청산 후보' : 'Critical Exit Candidates';
  String get limitedLiveAutoBuy =>
      isKorean ? '제한된 실자동매수' : 'Limited Live Auto Buy';
  String get limitedLiveAutoSell =>
      isKorean ? '제한형 실자동매도' : 'Limited Live Auto Sell';
  String get disabledByDefault => isKorean ? '기본 비활성화' : 'Disabled by Default';
  String get maxOnePerDay => isKorean ? '하루 최대 1회' : 'Max 1 Per Day';
  String get readinessRequired => isKorean ? '준비 점검 필요' : 'Readiness Required';
  String get heldPositionsOnly =>
      isKorean ? '보유 포지션 전용' : 'Held Positions Only';
  String get riskReductionOnly =>
      isKorean ? '리스크 축소 전용' : 'Risk Reduction Only';
  String get liveOrderConditions =>
      isKorean ? '실주문 가능 조건' : 'Live Order Conditions';
  String get autoBuyBlocked => isKorean ? '자동매수 차단됨' : 'Auto Buy Blocked';
  String get autoBuySubmitted => isKorean ? '자동매수 제출됨' : 'Auto Buy Submitted';
  String get autoBuyResult => isKorean ? '자동매수 결과' : 'Auto Buy Result';
  String get autoSellBlocked => isKorean ? '자동매도 차단됨' : 'Auto Sell Blocked';
  String get autoSellSubmitted => isKorean ? '자동매도 제출됨' : 'Auto Sell Submitted';
  String get autoSellResult => isKorean ? '자동매도 결과' : 'Auto Sell Result';
  String get latestRun => isKorean ? '최근 실행' : 'Latest Run';
  String get liveOrderSubmittedTitle =>
      isKorean ? '실주문 제출됨' : 'Live Order Submitted';
  String get noAutoRetryTitle => isKorean ? '자동 재시도 없음' : 'No Auto Retry';
  String get noBrokerSubmitTitle => isKorean ? '브로커 제출 없음' : 'No Broker Submit';
  String get brokerSubmitCalledTitle =>
      isKorean ? '브로커 제출 호출됨' : 'Broker Submit Called';
  String get refreshAutoBuyPhase1Status =>
      isKorean ? '자동매수 1단계 상태 새로고침' : 'Refresh Phase 1 Status';
  String get refreshAutoSellPhase1Status =>
      isKorean ? '자동매도 1단계 상태 새로고침' : 'Refresh Sell Phase 1 Status';
  String get runPhase1AttemptOnce =>
      isKorean ? '1단계 1회 시도' : 'Run Phase 1 Once';
  String get runPhase1SellAttemptOnce =>
      isKorean ? '1단계 매도 1회 시도' : 'Run Phase 1 Sell Once';
  String get liveOrderConditionsSummary => isKorean
      ? '명시적으로 활성화되고 dry_run=false, 킬 스위치 해제, KIS 실주문 허용, 운영 준비 완료, 포지션 점검 통과일 때만 제출됩니다.'
      : 'Submits only when explicitly enabled, dry_run=false, kill switch is off, KIS real orders are allowed, production readiness is ready, and position checks pass.';
  String get autoBuyPhase1AlreadyLoading => isKorean
      ? '자동매수 1단계 상태를 이미 불러오는 중입니다.'
      : 'Auto Buy Phase 1 status is already loading.';
  String autoBuyPhase1Refreshed(String status) => isKorean
      ? '자동매수 1단계 상태 새로고침 완료: $status.'
      : 'Auto Buy Phase 1 refreshed: $status.';
  String autoBuyPhase1Blocked(String reason) =>
      isKorean ? '자동매수 1단계 차단: $reason.' : 'Auto Buy Phase 1 blocked: $reason.';
  String get autoBuyPhase1Submitted =>
      isKorean ? '자동매수 1단계 주문이 제출되었습니다.' : 'Auto Buy Phase 1 order submitted.';
  String get autoSellPhase1AlreadyLoading => isKorean
      ? '자동매도 1단계 상태를 이미 불러오는 중입니다.'
      : 'Auto Sell Phase 1 status is already loading.';
  String autoSellPhase1Refreshed(String status) => isKorean
      ? '자동매도 1단계 상태 새로고침 완료: $status.'
      : 'Auto Sell Phase 1 refreshed: $status.';
  String autoSellPhase1Blocked(String reason) => isKorean
      ? '자동매도 1단계 차단: $reason.'
      : 'Auto Sell Phase 1 blocked: $reason.';
  String get autoSellPhase1Submitted =>
      isKorean ? '자동매도 1단계 주문이 제출되었습니다.' : 'Auto Sell Phase 1 order submitted.';
  String get portfolioOrchestratorAlreadyLoading => isKorean
      ? '포트폴리오 자동 운영 상태를 이미 불러오는 중입니다.'
      : 'Portfolio Orchestrator status is already loading.';
  String portfolioOrchestratorRefreshed(String status) => isKorean
      ? '포트폴리오 자동 운영 상태 새로고침 완료: $status.'
      : 'Portfolio Orchestrator refreshed: $status.';
  String portfolioOrchestratorCompleted(String status) => isKorean
      ? '포트폴리오 자동 운영 1회 실행 완료: $status.'
      : 'Portfolio Orchestrator run completed: $status.';
  String portfolioOrchestratorBlocked(String reason) => isKorean
      ? '포트폴리오 자동 운영 차단: $reason.'
      : 'Portfolio Orchestrator blocked: $reason.';
  String get portfolioOrchestratorSellSubmitted => isKorean
      ? '포트폴리오 자동 운영에서 매도 주문이 제출되었습니다.'
      : 'Portfolio Orchestrator submitted a sell order.';
  String get portfolioOrchestratorBuySubmitted => isKorean
      ? '포트폴리오 자동 운영에서 매수 주문이 제출되었습니다.'
      : 'Portfolio Orchestrator submitted a buy order.';
  String get selectedPromotion => isKorean ? '선택된 프로모션' : 'Selected Promotion';
  String get selectedExitCandidate =>
      isKorean ? '선택된 청산 후보' : 'Selected Exit Candidate';
  String get selectedSymbol => isKorean ? '선택 종목' : 'Selected Symbol';
  String get candidateType => isKorean ? '후보 유형' : 'Candidate Type';
  String get candidateSeverity => isKorean ? '후보 심각도' : 'Candidate Severity';
  String get sellPreflightStatus =>
      isKorean ? '매도 사전 점검 상태' : 'Sell Preflight Status';
  String get dailyLimit => isKorean ? '일일 한도' : 'Daily Limit';
  String get usedRemaining => isKorean ? '사용 / 남음' : 'Used / Remaining';
  String get maxAllowedNotional =>
      isKorean ? '허용 최대 주문금액' : 'Max Allowed Notional';
  String get noAutoBuyYet =>
      isKorean ? '아직 자동매수 실행 내역이 없습니다.' : 'No auto-buy run yet.';
  String get noAutoSellYet =>
      isKorean ? '아직 자동매도 실행 내역이 없습니다.' : 'No auto-sell run yet.';
  String get exitCandidateRequired =>
      isKorean ? '청산 후보 필요' : 'Exit Candidate Required';
  String get stopLossTakeProfitCandidate =>
      isKorean ? '손절/익절 후보' : 'Stop-Loss / Take-Profit Candidate';
  String promotionTraceCount(int count) {
    if (isKorean) return '프로모션 추적 $count건';
    return '$count promotion trace${count == 1 ? '' : 's'}';
  }

  String get refreshAutoBuyStatus =>
      isKorean ? '자동매수 상태 새로고침' : 'Refresh Auto Buy Status';
  String get refreshSchedulerStatus =>
      isKorean ? '스케줄러 상태 새로고침' : 'Refresh Scheduler Status';
  String get refreshPromotions => isKorean ? '프로모션 새로고침' : 'Refresh Promotions';
  String get dailyOperationsSummary =>
      isKorean ? '일일 운영 요약' : 'Daily Operations Summary';
  String get operatorAlertCenter =>
      isKorean ? '운영 알림 센터' : 'Operator Alert Center';
  String get riskAlerts => isKorean ? '위험 알림' : 'Risk Alerts';
  String get critical => isKorean ? '심각' : 'Critical';
  String get info => isKorean ? '정보' : 'Info';
  String get rejectedOrder => isKorean ? '거절된 주문' : 'Rejected Order';
  String get stalePromotion => isKorean ? '오래된 프로모션' : 'Stale Promotion';
  String get primaryReason => isKorean ? '주요 사유' : 'Primary Reason';
  String get nextSafeAction => isKorean ? '다음 안전 조치' : 'Next Safe Action';
  String get relatedItem => isKorean ? '관련 항목' : 'Related Item';
  String get refreshAlerts => isKorean ? '새로고침' : 'Refresh';
  String get operatorReadOnly => isKorean ? '읽기 전용' : 'Read Only';
  String get operatorNoLiveOrders => isKorean ? '실주문 없음' : 'No Live Orders';
  String get automationModeControl =>
      isKorean ? '자동화 모드 제어' : 'Automation Mode Control';
  String get automationModeControlSubtitle => isKorean
      ? '자동화 계층의 모드만 바꾸며 독립 안전 게이트는 그대로 둡니다.'
      : 'Changes only automation-layer mode flags; independent safety gates remain separate.';
  String get automationOff => isKorean ? '자동화 끄기' : 'Automation Off';
  String get monitoringOnly => isKorean ? '모니터링 전용' : 'Monitoring Only';
  String get dryRunAutomation => isKorean ? '드라이런 자동화' : 'Dry-Run Automation';
  String get phase1LiveReady => isKorean ? '1단계 실거래 준비' : 'Phase 1 Live Ready';
  String get liveOrderEligibility =>
      isKorean ? '실주문 가능 여부' : 'Live Order Eligibility';
  String get currentMode => isKorean ? '현재 모드' : 'Current Mode';
  String get effectiveStatus => isKorean ? '적용 상태' : 'Effective Status';
  String get blockingReasons => isKorean ? '차단 사유' : 'Blocking Reasons';
  String get warningReasons => isKorean ? '주의 사유' : 'Warning Reasons';
  String get independentSafetyGatesRequired =>
      isKorean ? '독립 안전 게이트 필요' : 'Independent Safety Gates Required';
  String get dryRunIsSeparate =>
      isKorean ? '드라이런은 별도입니다' : 'Dry-run is separate';
  String get killSwitchIsSeparate =>
      isKorean ? '킬 스위치는 별도입니다' : 'Kill switch is separate';
  String get kisRealOrdersAreSeparate =>
      isKorean ? 'KIS 실주문 설정은 별도입니다' : 'KIS real orders are separate';
  String get turnOffAutomation => isKorean ? '자동화 끄기' : 'Turn Off Automation';
  String get changeWithRiskAcknowledgement =>
      isKorean ? '위험 인지 후 변경' : 'Change with Risk Acknowledgement';
  String get selectAutomationMode =>
      isKorean ? '자동화 모드 선택' : 'Select Automation Mode';
  String get optionalReason => isKorean ? '선택 사유' : 'Optional Reason';
  String get operatorRiskAcknowledgement => isKorean
      ? '운영자가 모드 변경 위험을 확인했습니다.'
      : 'Operator acknowledges the risks of changing this mode.';
  String get acknowledgementRequiredForMode => isKorean
      ? '이 모드는 위험 인지가 필요합니다.'
      : 'This mode requires risk acknowledgement.';
  String get automationModeStatusAlreadyLoading => isKorean
      ? '자동화 모드 상태를 이미 불러오는 중입니다.'
      : 'Automation mode status is already loading.';
  String automationModeStatusRefreshed(String status) => isKorean
      ? '자동화 모드 상태 새로고침 완료: $status.'
      : 'Automation mode status refreshed: $status.';
  String automationModeChanged(String mode) =>
      isKorean ? '자동화 모드 변경 완료: $mode.' : 'Automation mode changed: $mode.';
  String get automationModeTurnedOff =>
      isKorean ? '자동화 모드가 꺼졌습니다.' : 'Automation mode turned off.';
  String get automationModeNotLoaded => isKorean
      ? '자동화 모드 상태를 아직 불러오지 않았습니다.'
      : 'Automation mode status not loaded.';
  String get liveOrdersRemainBlocked => isKorean
      ? '독립 안전 게이트가 모두 통과할 때까지 실주문은 계속 차단됩니다.'
      : 'Live orders remain blocked until independent gates pass.';
  String get automationModeModules =>
      isKorean ? '자동화 모듈' : 'Automation Modules';
  String get noBrokerSubmitModeControl =>
      isKorean ? '브로커 제출 없음' : 'No Broker Submit';
  String get modeUpdated => isKorean ? '모드 변경 시각' : 'Mode Updated';
  String automationModeLabel(String mode) {
    switch (mode.trim().toLowerCase()) {
      case 'monitor_only':
        return monitoringOnly;
      case 'dry_run_auto':
        return dryRunAutomation;
      case 'phase1_live_ready':
        return phase1LiveReady;
      case 'off':
      default:
        return automationOff;
    }
  }

  String automationControlLabel(String value) {
    final normalized = value.trim().toLowerCase();
    final ko = <String, String>{
      'off': '꺼짐',
      'monitoring': '모니터링',
      'dry_run_ready': '드라이런 준비',
      'live_ready_blocked': '실거래 준비 차단',
      'live_ready': '실거래 준비',
      'automation_mode_off': '자동화 모드 꺼짐',
      'phase1_live_disabled_in_monitor_only': '모니터링 전용에서 1단계 실거래 차단',
      'phase1_live_disabled_in_dry_run_auto': '드라이런 자동화에서 1단계 실거래 차단',
      'dry_run_enabled': '드라이런 켜짐',
      'kill_switch_enabled': '킬 스위치 켜짐',
      'kis_disabled': 'KIS 비활성',
      'kis_real_order_disabled': 'KIS 실주문 비활성',
      'production_readiness_not_ready': '운영 준비 미완료',
      'portfolio_orchestrator_disabled': '포트폴리오 오케스트레이터 비활성',
      'portfolio_orchestrator_live_orders_disabled': '오케스트레이터 실주문 비활성',
      'auto_buy_live_phase1_disabled': '자동매수 1단계 비활성',
      'auto_buy_live_phase1_real_orders_disabled': '자동매수 1단계 실주문 비활성',
      'auto_sell_live_phase1_disabled': '자동매도 1단계 비활성',
      'auto_sell_live_phase1_real_orders_disabled': '자동매도 1단계 실주문 비활성',
      'pending_order_blocker_exists': '대기 주문 차단 항목 있음',
      'sync_required_order_exists': '동기화 필요 주문 있음',
      'daily_trade_limit_reached': '일일 거래 한도 도달',
      'dry_run_is_separate': dryRunIsSeparate,
      'kill_switch_is_separate': killSwitchIsSeparate,
      'kis_real_orders_are_separate': kisRealOrdersAreSeparate,
      'production_readiness_needs_review': '운영 준비 상태 검토 필요',
      'automation_is_off': '자동화가 꺼져 있습니다',
      'review_monitoring_status': '모니터링 상태 검토',
      'review_dry_run_results': '드라이런 결과 검토',
      'run_phase1_orchestrator_only_if_operator_intends':
          '운영자가 의도할 때만 1단계 오케스트레이터 검토',
      'review_phase1_live_readiness': '1단계 실거래 준비 상태 검토',
      'review_dry_run_setting_without_changing_it_here':
          '여기서 변경하지 말고 드라이런 설정 검토',
      'review_kill_switch_without_changing_it_here': '여기서 변경하지 말고 킬 스위치 검토',
      'review_broker_real_order_setting_separately': '브로커 실주문 설정 별도 검토',
      'review_production_readiness': '운영 준비 상태 검토',
      'review_pending_orders': '대기 주문 검토',
      'reconcile_orders_before_live_automation': '실거래 자동화 전 주문 동기화',
      'wait_for_next_trading_day': '다음 거래일까지 대기',
      'review_blocking_reasons': '차단 사유 검토',
    };
    final en = <String, String>{
      'off': 'Off',
      'monitoring': 'Monitoring',
      'dry_run_ready': 'Dry-run Ready',
      'live_ready_blocked': 'Live Ready Blocked',
      'live_ready': 'Live Ready',
      'automation_mode_off': 'Automation Mode Off',
      'phase1_live_disabled_in_monitor_only':
          'Phase 1 live disabled in Monitoring Only',
      'phase1_live_disabled_in_dry_run_auto':
          'Phase 1 live disabled in Dry-Run Automation',
      'dry_run_enabled': 'Dry-run enabled',
      'kill_switch_enabled': 'Kill switch enabled',
      'kis_disabled': 'KIS disabled',
      'kis_real_order_disabled': 'KIS real orders disabled',
      'production_readiness_not_ready': 'Production readiness not ready',
      'portfolio_orchestrator_disabled': 'Portfolio orchestrator disabled',
      'portfolio_orchestrator_live_orders_disabled':
          'Portfolio orchestrator live orders disabled',
      'auto_buy_live_phase1_disabled': 'Auto buy Phase 1 disabled',
      'auto_buy_live_phase1_real_orders_disabled':
          'Auto buy Phase 1 real orders disabled',
      'auto_sell_live_phase1_disabled': 'Auto sell Phase 1 disabled',
      'auto_sell_live_phase1_real_orders_disabled':
          'Auto sell Phase 1 real orders disabled',
      'pending_order_blocker_exists': 'Pending order blocker exists',
      'sync_required_order_exists': 'Sync-required order exists',
      'daily_trade_limit_reached': 'Daily trade limit reached',
      'dry_run_is_separate': dryRunIsSeparate,
      'kill_switch_is_separate': killSwitchIsSeparate,
      'kis_real_orders_are_separate': kisRealOrdersAreSeparate,
      'production_readiness_needs_review': 'Production readiness needs review',
      'automation_is_off': 'Automation is off',
      'review_monitoring_status': 'Review monitoring status',
      'review_dry_run_results': 'Review dry-run results',
      'run_phase1_orchestrator_only_if_operator_intends':
          'Review Phase 1 orchestrator only if the operator intends',
      'review_phase1_live_readiness': 'Review Phase 1 live readiness',
      'review_dry_run_setting_without_changing_it_here':
          'Review dry-run setting without changing it here',
      'review_kill_switch_without_changing_it_here':
          'Review kill switch without changing it here',
      'review_broker_real_order_setting_separately':
          'Review broker real-order setting separately',
      'review_production_readiness': 'Review production readiness',
      'review_pending_orders': 'Review pending orders',
      'reconcile_orders_before_live_automation':
          'Reconcile orders before live automation',
      'wait_for_next_trading_day': 'Wait for next trading day',
      'review_blocking_reasons': 'Review blocking reasons',
    };
    return isKorean
        ? (ko[normalized] ?? _automationFallbackLabel(normalized))
        : (en[normalized] ?? _automationFallbackLabel(normalized));
  }

  String get autoExitCandidates =>
      isKorean ? '자동 청산 후보' : 'Auto Exit Candidates';
  String get positionMonitoring =>
      isKorean ? '보유 종목 자동 감시' : 'Position Monitoring';
  String get stopLossCandidate => isKorean ? '손절 후보' : 'Stop-Loss Candidate';
  String get takeProfitCandidate =>
      isKorean ? '익절 후보' : 'Take-Profit Candidate';
  String get trendBreakdown => isKorean ? '추세 이탈' : 'Trend Breakdown';
  String get weakMomentum => isKorean ? '모멘텀 약화' : 'Weak Momentum';
  String get nearCloseRisk => isKorean ? '장마감 리스크' : 'Near-Close Risk';
  String get duplicateSellOrder =>
      isKorean ? '중복 매도 주문' : 'Duplicate Sell Order';
  String get manualReviewRequired =>
      isKorean ? '수동 검토 필요' : 'Manual Review Required';
  String get refreshExitCandidates =>
      isKorean ? '청산 후보 새로고침' : 'Refresh Exit Candidates';
  String get totalCandidates => isKorean ? '전체 후보' : 'Total Candidates';
  String get thresholdValues => isKorean ? '임계값' : 'Threshold Values';
  String get relatedReferences => isKorean ? '관련 참조' : 'Related References';
  String get autoExitCandidatesAlreadyLoading => isKorean
      ? '자동 청산 후보를 이미 불러오는 중입니다.'
      : 'Auto exit candidates are already loading.';
  String autoExitCandidatesRefreshed(int count) => isKorean
      ? '자동 청산 후보 새로고침 완료: $count건.'
      : 'Auto exit candidates refreshed: $count.';
  String sellPreflightBlockedForCandidate(String reason) => isKorean
      ? '이 후보는 매도 사전 점검을 실행할 수 없습니다: $reason.'
      : 'Sell preflight is disabled for this candidate: $reason.';
  String get positionManagementDryRun =>
      isKorean ? '포지션 자동관리 드라이런' : 'Position Management Dry-Run';
  String get positionsFirst => isKorean ? '보유 종목 우선 점검' : 'Positions First';
  String get autoExitCandidateCheck =>
      isKorean ? '자동 청산 후보 점검' : 'Auto Exit Candidate Check';
  String get noSellExecution => isKorean ? '매도 실행 없음' : 'No Sell Execution';
  String get positionsChecked => isKorean ? '점검 포지션' : 'Positions Checked';
  String get exitCandidates => isKorean ? '청산 후보' : 'Exit Candidates';
  String get criticalCandidates => isKorean ? '중요 후보' : 'Critical Candidates';
  String get latestRunResult => isKorean ? '최근 실행 결과' : 'Latest Run Result';
  String get runPositionManagementDryRunOnce =>
      isKorean ? '포지션 자동관리 드라이런 1회 실행' : 'Run Position Management Dry-Run Once';
  String get refreshPositionManagementDryRun =>
      isKorean ? '포지션 자동관리 드라이런 새로고침' : 'Refresh Position Management Dry-Run';
  String get positionManagementDryRunAlreadyLoading => isKorean
      ? '포지션 자동관리 드라이런을 이미 불러오는 중입니다.'
      : 'Position management dry-run is already loading.';
  String positionManagementDryRunRefreshed(int count) => isKorean
      ? '포지션 자동관리 드라이런 새로고침 완료: 청산 후보 $count건.'
      : 'Position management dry-run refreshed: $count exit candidates.';
  String positionManagementDryRunCompleted(String status, int count) => isKorean
      ? '포지션 자동관리 드라이런 완료: $status / 청산 후보 $count건.'
      : 'Position management dry-run completed: $status / $count exit candidates.';
  String autoExitCandidateTypeLabel(String type) {
    switch (type) {
      case 'stop_loss':
        return stopLossCandidate;
      case 'take_profit':
        return takeProfitCandidate;
      case 'trend_breakdown':
        return trendBreakdown;
      case 'weak_momentum':
        return weakMomentum;
      case 'near_close_risk':
        return nearCloseRisk;
      case 'duplicate_sell_conflict':
        return duplicateSellOrder;
      case 'sync_required':
        return syncRequired;
      case 'manual_review':
        return manualReviewRequired;
    }
    return type.replaceAll('_', ' ');
  }

  String autoExitSeverityLabel(String severity) {
    switch (severity) {
      case 'critical':
        return critical;
      case 'warning':
        return warning;
      case 'info':
        return info;
    }
    return severity;
  }

  String get productionReadiness =>
      isKorean ? '운영 준비 점검' : 'Production Readiness';
  String get productionReadinessRefreshInProgress => isKorean
      ? '운영 준비 점검 새로고침 중입니다.'
      : 'Production readiness refresh already in progress.';
  String get liveReadinessStatus =>
      isKorean ? '실전 준비 상태' : 'Live Readiness Status';
  String get readinessReady => isKorean ? '준비 완료' : 'Ready';
  String get readinessWarning => isKorean ? '주의 필요' : 'Warning';
  String get readinessBlocked => isKorean ? '차단됨' : 'Blocked';
  String get readinessUnknown => isKorean ? '확인 불가' : 'Unknown';
  String readinessStatusLabel(String status) {
    switch (status.toLowerCase()) {
      case 'ready':
        return readinessReady;
      case 'warning':
      case 'warn':
        return readinessWarning;
      case 'blocked':
      case 'fail':
        return readinessBlocked;
      default:
        return readinessUnknown;
    }
  }

  String productionReadinessStatus(String status) =>
      isKorean ? '운영 준비 상태: $status.' : 'Production readiness: $status.';
  String get primaryBlockReasons =>
      isKorean ? '주요 차단 사유' : 'Primary Block Reasons';
  String get runtimeSettings => isKorean ? '런타임 설정' : 'Runtime Settings';
  String get schedulerSafety => isKorean ? '스케줄러 안전' : 'Scheduler Safety';
  String get orderReconciliation => isKorean ? '주문 대조' : 'Order Reconciliation';
  String get positionsPnl => isKorean ? '포지션 / 손익' : 'Positions / P&L';
  String get alertStatus => isKorean ? '알림 상태' : 'Alert Status';
  String get agentChatSafety => isKorean ? '에이전트 채팅 안전' : 'Agent Chat Safety';
  String get guardedBuy => isKorean ? '가드 매수' : 'Guarded Buy';
  String get guardedSell => isKorean ? '가드 매도' : 'Guarded Sell';
  String get databaseStatus => isKorean ? '데이터베이스' : 'Database';
  String get automationUnlockNotAllowed =>
      isKorean ? '자동화 해제 불가' : 'Automation Unlock Not Allowed';
  String get refreshProductionReadiness =>
      isKorean ? '운영 준비 점검 새로고침' : 'Refresh Production Readiness';
  String get blockedChecks => isKorean ? '차단 항목' : 'Blocked Checks';
  String get groupedChecklist => isKorean ? '체크리스트' : 'Checklist';
  String get schedulerDryRunOnly =>
      isKorean ? '스케줄러 모의 실행 전용' : 'Scheduler Dry-Run Only';
  String get noOperatorAlerts =>
      isKorean ? '활성 운영 알림이 없습니다.' : 'No active alerts.';
  String get operatorAlertsAlreadyLoading => isKorean
      ? '운영 알림을 이미 불러오는 중입니다.'
      : 'Operator alerts are already loading.';
  String operatorAlertsRefreshed(int count) => isKorean
      ? '운영 알림 새로고침 완료: 활성 $count건'
      : 'Operator alerts refreshed: $count active.';
  String get refreshDailySummary =>
      isKorean ? '일일 운영 요약 새로고침' : 'Refresh Daily Summary';
  String get brokerReconciliation =>
      isKorean ? '브로커 대사' : 'Broker Reconciliation';
  String get todaysTradeActivity =>
      isKorean ? '오늘 거래 활동' : 'Today\'s Trade Activity';
  String get plSummary => isKorean ? '손익 요약' : 'P/L Summary';
  String get orderSummary => isKorean ? '주문 요약' : 'Order Summary';
  String get promotionSummary => isKorean ? '프로모션 요약' : 'Promotion Summary';
  String get schedulerSummary => isKorean ? '스케줄러 요약' : 'Scheduler Summary';
  String get riskSummary => isKorean ? '리스크 요약' : 'Risk Summary';
  String get attentionRequired => isKorean ? '확인 필요' : 'Attention Required';
  String get okStatus => isKorean ? '정상' : 'OK';
  String get nextSafeActions => isKorean ? '다음 안전 조치' : 'Next Safe Actions';
  String get ordersToday => isKorean ? '오늘 주문' : 'Orders Today';
  String get promotionsPending =>
      isKorean ? '대기 중인 프로모션' : 'Promotions Pending';
  String get blockedAttempts => isKorean ? '차단된 시도' : 'Blocked Attempts';
  String get generatedAt => isKorean ? '생성 시각' : 'Generated At';
  String get detailsLabel => isKorean ? '상세' : 'Details';
  String get localDbOnly => isKorean ? '로컬 DB 전용' : 'LOCAL DB ONLY';
  String get noSync => isKorean ? '동기화 없음' : 'NO SYNC';
  String get noRetry => isKorean ? '재시도 없음' : 'NO RETRY';
  String get dailyOpsSummaryAlreadyLoading => isKorean
      ? '일일 운영 요약을 이미 불러오는 중입니다.'
      : 'Daily operations summary is already loading.';
  String dailyOpsSummaryRefreshed(int orderCount) => isKorean
      ? '일일 운영 요약 새로고침 완료: 주문 $orderCount건.'
      : 'Daily operations summary refreshed: $orderCount orders.';
  String get enableDryRunScheduler =>
      isKorean ? '드라이런 스케줄러 켜기' : 'Enable Dry-Run Scheduler';
  String get disableScheduler => isKorean ? '스케줄러 끄기' : 'Disable Scheduler';
  String get runDryRunOnce => isKorean ? '드라이런 1회 실행' : 'Run Dry-Run Once';
  String get runDryRunAutoBuyOnce =>
      isKorean ? '드라이런 자동매수 1회 실행' : 'Run Dry-Run Auto Buy Once';
  String get runGuardedLiveAutoBuyOnce =>
      isKorean ? '보호된 실매수 1회 실행' : 'Run Guarded Live Auto Buy Once';
  String get confirmGuardedLiveAutoBuy =>
      isKorean ? '보호된 실매수 확인' : 'Confirm Guarded Live Auto Buy';
  String guardedLiveAutoBuyReady(String profile) => isKorean
      ? '프로필 $profile에서 보호된 실매수 1회 실행이 준비되었습니다.'
      : 'Profile $profile is ready for a one-shot guarded live buy.';

  String get dryRunOnly => isKorean ? '드라이런 전용' : 'DRY-RUN ONLY';
  String get promotionQueueOnly =>
      isKorean ? '프로모션 목록 전용' : 'PROMOTION QUEUE ONLY';
  String get noLiveOrders => isKorean ? '실주문 없음' : 'NO LIVE ORDERS';
  String get schedulerRealOrdersDisabled =>
      isKorean ? '스케줄러 실주문 비활성화' : 'SCHEDULER REAL ORDERS DISABLED';
  String get noValidationInScheduler =>
      isKorean ? '스케줄러 검증 없음' : 'NO VALIDATION IN SCHEDULER';
  String get noBrokerSubmitInScheduler =>
      isKorean ? '스케줄러 증권사 제출 없음' : 'NO BROKER SUBMIT IN SCHEDULER';
  String get promotionOnly => isKorean ? '프로모션 전용' : 'PROMOTION ONLY';
  String get reviewRequired => isKorean ? '검토 필요' : 'REVIEW REQUIRED';
  String get notAnOrder => isKorean ? '주문 아님' : 'NOT AN ORDER';
  String get noBrokerSubmit => isKorean ? '브로커 제출 없음' : 'NO BROKER SUBMIT';
  String get liveConversionRequiresFinalConfirmation => isKorean
      ? '실거래 전환은 최종 확인 필요'
      : 'LIVE CONVERSION REQUIRES FINAL CONFIRMATION';
  String get autoBuyOps => isKorean ? '자동매수 운영' : 'AUTO BUY OPS';
  String get dryRunEvidenceRequired =>
      isKorean ? '드라이런 근거 필요' : 'DRY RUN EVIDENCE REQUIRED';
  String get targetRiskGated => isKorean ? '목표 위험 게이트 적용' : 'TARGET RISK GATED';
  String get kisValidationRequired =>
      isKorean ? '한국투자증권 검증 필요' : 'KIS VALIDATION REQUIRED';
  String get oneShotLiveBuy => isKorean ? '단발 실매수' : 'ONE SHOT LIVE BUY';
  String get scheduledDryRun => isKorean ? '예약 드라이런' : 'SCHEDULED DRY RUN';
  String get noLiveScheduler => isKorean ? '실거래 스케줄러 없음' : 'NO LIVE SCHEDULER';
  String get noAutoRetry => isKorean ? '자동 재시도 없음' : 'NO AUTO RETRY';

  String get stage => isKorean ? '단계' : 'Stage';
  String get latestDryRun => isKorean ? '최근 드라이런' : 'Latest dry-run';
  String get dryRunScore => isKorean ? '드라이런 점수' : 'Dry-run score';
  String get dryRunTime => isKorean ? '드라이런 시각' : 'Dry-run time';
  String get readiness => isKorean ? '준비 상태' : 'Readiness';
  String get ordersRemaining => isKorean ? '남은 주문 수' : 'Orders remaining';
  String get latestLiveAttempt =>
      isKorean ? '최근 실거래 시도' : 'Latest live attempt';
  String get scheduler => isKorean ? '스케줄러' : 'Scheduler';
  String get promotions => isKorean ? '프로모션' : 'Promotions';
  String get nextAction => isKorean ? '다음 조치' : 'Next action';
  String get liveOrdersAllowed => isKorean ? '실주문 허용' : 'Live orders allowed';
  String get realOrderSubmitAllowed =>
      isKorean ? '실주문 제출 허용' : 'Real order submit allowed';
  String get activeProfile => isKorean ? '활성 프로필' : 'Active profile';
  String get runsToday => isKorean ? '오늘 실행' : 'Runs today';
  String get nextAllowedRun => isKorean ? '다음 허용 실행' : 'Next allowed run';
  String get blockReason => isKorean ? '차단 사유' : 'Block reason';
  String get pendingPromotions => isKorean ? '대기 프로모션' : 'Pending promotions';

  String get noPromotionTraces =>
      isKorean ? '프로모션 추적이 없습니다.' : 'No promotion traces.';
  String get score => isKorean ? '점수' : 'Score';
  String get confidence => isKorean ? '신뢰도' : 'Confidence';
  String get proposed => isKorean ? '제안 금액' : 'Proposed';
  String get maxNotional => isKorean ? '최대 금액' : 'Max notional';
  String get qty => isKorean ? '수량' : 'Qty';
  String get price => isKorean ? '가격' : 'Price';
  String get expires => isKorean ? '만료' : 'Expires';
  String get age => isKorean ? '경과' : 'Age';
  String get liveAttempt => isKorean ? '실거래 시도' : 'Live attempt';
  String get order => isKorean ? '주문' : 'Order';
  String get sync => isKorean ? '동기화' : 'Sync';
  String get review => isKorean ? '검토' : 'Review';
  String get action => isKorean ? '동작' : 'Action';
  String get reason => isKorean ? '사유' : 'Reason';
  String get summary => isKorean ? '요약' : 'Summary';
  String get riskNote => isKorean ? '위험 메모' : 'Risk note';
  String get dryRunIds => isKorean ? '드라이런 ID' : 'Dry-run IDs';
  String get riskFlags => isKorean ? '위험 사유' : 'Risk flags';
  String get gates => isKorean ? '게이트' : 'Gates';
  String get warning => isKorean ? '경고' : 'Warning';
  String get checklist => isKorean ? '체크리스트' : 'Checklist';
  String get conversion => isKorean ? '전환' : 'Conversion';
  String get lastSync => isKorean ? '마지막 동기화' : 'Last sync';
  String get trace => isKorean ? '추적' : 'Trace';
  String get markReviewed => isKorean ? '검토 완료 표시' : 'Mark Reviewed';
  String get dismiss => isKorean ? '제외' : 'Dismiss';
  String get convertViaGuardedLiveBuy =>
      isKorean ? '보호된 실매수로 전환' : 'Convert via Guarded Live Buy';
  String get converted => isKorean ? '전환됨' : 'CONVERTED';
  String get promotionExpiredWarning => isKorean
      ? '프로모션이 만료되었거나 오래되어 전환이 차단되었습니다.'
      : 'Promotion is expired or stale. Conversion is blocked.';
  String convertPromotionConfirm(String symbol) => isKorean
      ? '$symbol 후보를 기존 보호된 실매수 엔드포인트로 전환합니다. 이 프로모션은 주문이 아니며 스케줄러는 아무 주문도 제출하지 않습니다.'
      : 'Convert $symbol via the existing guarded live auto-buy endpoint. This promotion is not an order and the scheduler will not submit anything.';

  String get preflightLiveBuy =>
      isKorean ? '매수 전환 사전 점검' : 'Preflight Live Buy';
  String get preflightResult => isKorean ? '사전 점검 결과' : 'Preflight Result';
  String get allowed => isKorean ? '전환 가능' : 'Allowed';
  String get finalConfirmationRequiredShort =>
      isKorean ? '최종 확인 필요' : 'Final confirmation required';
  String get noLiveOrderSubmitted =>
      isKorean ? '실주문 없음' : 'No Live Order Submitted';
  String get primaryBlockReason =>
      isKorean ? '주요 차단 사유' : 'Primary Block Reason';
  String get preflightChecklist => isKorean ? '점검 목록' : 'Checklist';
  String get estimatedNotional => isKorean ? '예상 주문 금액' : 'Estimated notional';
  String get availableCash => isKorean ? '사용 가능 예수금' : 'Available cash';
  String get gatingNotes => isKorean ? '차단/검토 사유' : 'Gating notes';
  String get liveBuyConversionResult =>
      isKorean ? '실매수 전환 결과' : 'Live Buy Conversion Result';
  String get liveOrderSubmitted =>
      isKorean ? '실주문 제출됨' : 'Live Order Submitted';
  String get brokerOrderId => isKorean ? '브로커 주문 번호' : 'Broker Order ID';
  String get kisOrderNo => isKorean ? '한국투자증권 주문번호' : 'KIS Order No.';
  String get relatedOrderLog => isKorean ? '주문 로그' : 'Order Log';
  String get filledQuantity => isKorean ? '체결 수량' : 'Filled Quantity';
  String get submittedQuantity => isKorean ? '제출 수량' : 'Submitted Quantity';
  String get averageFillPrice => isKorean ? '평균 체결가' : 'Average Fill Price';
  String get filledNotional => isKorean ? '체결 금액' : 'Filled Notional';
  String get syncOrderStatus => isKorean ? '주문 상태 동기화' : 'Sync Order Status';
  String get refreshResult => isKorean ? '결과 새로고침' : 'Refresh Result';
  String get backToPromotionQueue =>
      isKorean ? '프로모션 목록으로 돌아가기' : 'Back to Promotion Queue';
  String get auditTrace => isKorean ? '감사 추적' : 'Audit Trace';
  String get internalStatus => isKorean ? '내부 상태' : 'Internal Status';
  String get brokerStatus => isKorean ? '브로커 상태' : 'Broker Status';
  String get syncRequired => isKorean ? '동기화 필요' : 'Sync Required';
  String get liveBuyResultAlreadyLoading => isKorean
      ? '실매수 전환 결과를 이미 불러오는 중입니다.'
      : 'Live buy result is already loading.';
  String liveBuyResultRefreshed(String status) => isKorean
      ? '전환 결과 새로고침 완료: $status.'
      : 'Conversion result refreshed: $status.';
  String liveBuyResultSynced(String status) =>
      isKorean ? '주문 상태 동기화 완료: $status.' : 'Order status synced: $status.';
  String get preflightAlreadyRunning => isKorean
      ? '매수 전환 사전 점검이 이미 실행 중입니다.'
      : 'Live buy preflight is already running.';
  String preflightCompletedMessage(String status, String? reason) {
    final label = statusLabel(status);
    if (reason == null || reason.trim().isEmpty) {
      return isKorean ? '사전 점검 완료: $label.' : 'Preflight completed: $label.';
    }
    return isKorean
        ? '사전 점검 완료: $label / $reason.'
        : 'Preflight completed: $label / $reason.';
  }

  String preflightBlocksConversion(String reason) => isKorean
      ? '사전 점검 결과 전환이 차단되었습니다: $reason.'
      : 'Preflight blocks conversion: $reason.';

  String get positionLifecycle =>
      isKorean ? '?ъ????앹븷二쇨린' : 'Position Lifecycle';
  String get tradeFlowAudit => isKorean ? '嫄곕옒 ?먮쫫 媛먯궗' : 'Trade Flow Audit';
  String get lifecycleOpen => isKorean ? '蹂댁쑀 以?' : 'Open';
  String get lifecycleClosed => isKorean ? '醫낅즺??' : 'Closed';
  String get entryLabel => isKorean ? '吏꾩엯' : 'Entry';
  String get exitLabel => isKorean ? '泥?궛' : 'Exit';
  String get realizedPl => isKorean ? '?ㅽ쁽?먯씡' : 'Realized P/L';
  String get averageExitPrice => isKorean ? '?됯퇏 留ㅻ룄媛' : 'Average Exit Price';
  String get holdingPeriod => isKorean ? '蹂댁쑀 湲곌컙' : 'Holding Period';
  String get relatedPromotion => isKorean ? '愿???꾨낫' : 'Related Promotion';
  String get relatedOrder => isKorean ? '愿??二쇰Ц' : 'Related Order';
  String get calculationIncomplete =>
      isKorean ? '怨꾩궛 遺덉셿??' : 'Calculation Incomplete';
  String get insufficientData => isKorean ? '?곗씠??遺議?' : 'Insufficient Data';
  String get refreshLifecycle =>
      isKorean ? '?ъ????앹븷二쇨린 ?덈줈怨좎묠' : 'Refresh Lifecycle';
  String get noLifecycleItems => isKorean
      ? '?쒖떆?????ъ????앹븷二쇨린媛 ?놁뒿?덈떎.'
      : 'No position lifecycle records.';
  String positionLifecycleRefreshed(int count) => isKorean
      ? '?ъ????앹븷二쇨린 ?덈줈怨좎묠 ?꾨즺: $count.'
      : 'Position lifecycle refreshed: $count.';

  String get positionExitReview =>
      isKorean ? '포지션 청산 검토' : 'Position Exit Review';
  String get heldPositions => isKorean ? '보유 포지션' : 'Held Positions';
  String get sellPreflight => isKorean ? '매도 사전 점검' : 'Sell Preflight';
  String get preflightOnly => isKorean ? '사전 점검 전용' : 'Preflight Only';
  String get noBrokerSubmitDisplay =>
      isKorean ? '브로커 제출 없음' : 'No Broker Submit';
  String get finalConfirmationRequiredDisplay =>
      isKorean ? '최종 확인 필요' : 'Final Confirmation Required';
  String get quantityHeld => isKorean ? '보유 수량' : 'Quantity Held';
  String get availableQuantity => isKorean ? '매도 가능 수량' : 'Available Quantity';
  String get averageEntryPrice => isKorean ? '평균 매수가' : 'Average Entry Price';
  String get currentPriceLabel => isKorean ? '현재가' : 'Current Price';
  String get marketValue => isKorean ? '평가금액' : 'Market Value';
  String get unrealizedPl => isKorean ? '평가손익' : 'Unrealized P/L';
  String get stopLossCondition => isKorean ? '손절 조건' : 'Stop-Loss Condition';
  String get takeProfitCondition =>
      isKorean ? '익절 조건' : 'Take-Profit Condition';
  String get nextRequiredAction =>
      isKorean ? '다음 필요 조치' : 'Next Required Action';
  String get refreshPositions => isKorean ? '보유 포지션 새로고침' : 'Refresh Positions';
  String get runSellPreflight =>
      isKorean ? '매도 사전 점검 실행' : 'Run Sell Preflight';
  String get backToPositions => isKorean ? '보유 포지션으로' : 'Back to Positions';
  String get requestedQuantity => isKorean ? '요청 수량' : 'Requested Quantity';
  String get symbolLabel => isKorean ? '종목' : 'Symbol';
  String get estimatedSellNotional =>
      isKorean ? '예상 매도 금액' : 'Estimated Sell Notional';
  String get noHeldPositions => isKorean ? '보유 포지션 없음.' : 'No held positions.';
  String get sellPreflightAlreadyRunning =>
      isKorean ? '매도 사전 점검이 이미 실행 중입니다.' : 'Sell preflight is already running.';
  String sellPreflightCompletedMessage(String status, String? reason) {
    final label = statusLabel(status);
    if (reason == null || reason.trim().isEmpty) {
      return isKorean
          ? '매도 사전 점검 완료: $label.'
          : 'Sell preflight completed: $label.';
    }
    return isKorean
        ? '매도 사전 점검 완료: $label / $reason.'
        : 'Sell preflight completed: $label / $reason.';
  }

  String get executeGuardedLiveSell =>
      isKorean ? '蹂댄샇???ㅻℓ???ㅽ뻾' : 'Execute Guarded Live Sell';
  String get liveSellExecutionResult =>
      isKorean ? '?ㅻℓ???ㅽ뻾 寃곌낵' : 'Live Sell Execution Result';
  String get guardedLiveSellConfirmTitle =>
      isKorean ? '蹂댄샇???ㅻℓ???뺤씤' : 'Confirm Guarded Live Sell';
  String get guardedLiveSellLiveWarning => isKorean
      ? 'dry_run=false이고 寃뚯씠?몄씠 ?덉슜?섎㈃ ?ㅼ＜臾몄쑝濡??쒖텧?⑸땲??'
      : 'This is a live sell order if dry_run=false and backend gates allow it.';
  String get guardedLiveSellDryRunWarning => isKorean
      ? 'dry_run=true ?곹깭?먯꽌??釉뚮줈而??쒖텧???놁뒿?덈떎.'
      : 'Dry-run is on, so no live sell will be submitted.';
  String guardedLiveSellConfirmBody({
    required String symbol,
    required String quantity,
    required String notional,
    required String unrealizedPl,
    required bool dryRun,
  }) {
    if (isKorean) {
      return '醫낅ぉ: $symbol\n留ㅻ룄 ?섎웾: $quantity\n?덉긽 留ㅻ룄 湲덉븸: $notional\n?됯??먯씡: $unrealizedPl\n?먮룞 ?ъ떆?????놁뒿?덈떎.\n${dryRun ? guardedLiveSellDryRunWarning : guardedLiveSellLiveWarning}';
    }
    return 'Symbol: $symbol\nSell quantity: $quantity\nEstimated sell notional: $notional\nUnrealized P/L: $unrealizedPl\nNo auto retry.\n${dryRun ? guardedLiveSellDryRunWarning : guardedLiveSellLiveWarning}';
  }

  String get sellQuantity => isKorean ? '留ㅻ룄 ?섎웾' : 'Sell Quantity';
  String get guardedLiveSellAlreadyRunning => isKorean
      ? '蹂댄샇???ㅻℓ???대? ?ㅽ뻾 以묒엯?덈떎.'
      : 'Guarded live sell is already running.';
  String get guardedLiveSellResultUnavailable =>
      isKorean ? '?ㅻℓ???ㅽ뻾 寃곌낵媛 ?놁뒿?덈떎.' : 'Live sell result is unavailable.';
  String get refreshGuardedLiveSellResult =>
      isKorean ? '寃곌낵 ?덈줈怨좎묠' : 'Refresh Result';

  String guardedLiveSellCompletedMessage(String status, String? reason) {
    final label = statusLabel(status);
    if (reason == null || reason.trim().isEmpty) {
      return isKorean
          ? '?ㅻℓ???ㅽ뻾 寃곌낵: $label.'
          : 'Live sell execution result: $label.';
    }
    return isKorean
        ? '?ㅻℓ???ㅽ뻾 寃곌낵: $label / $reason.'
        : 'Live sell execution result: $label / $reason.';
  }

  String guardedLiveSellResultRefreshed(String status) => isKorean
      ? '?ㅻℓ???ㅽ뻾 寃곌낵 ?덈줈怨좎묠 ?꾨즺: ${statusLabel(status)}.'
      : 'Live sell result refreshed: ${statusLabel(status)}.';

  String guardedLiveSellResultSynced(String status) => isKorean
      ? '二쇰Ц ?곹깭 ?숆린???꾨즺: ${statusLabel(status)}.'
      : 'Order status synced: ${statusLabel(status)}.';

  String preflightBlocksGuardedSell(String reason) => isKorean
      ? '留ㅻ룄 ?ъ쟾 ?먭? 寃곌낵 ?ㅽ뻾??李⑤떒?섏뿀?듬땲?? $reason.'
      : 'Sell preflight blocks execution: $reason.';

  String preflightChecklistLabel(String key) {
    final normalized = key.trim().toLowerCase();
    final ko = <String, String>{
      'promotion_exists': '프로모션 존재',
      'promotion_not_dismissed': '제외되지 않음',
      'promotion_not_expired': '만료되지 않음',
      'promotion_not_converted': '이미 전환되지 않음',
      'promotion_state_allowed': '프로모션 상태 허용',
      'promotion_scope_matches': '프로모션 범위 일치',
      'review_completed_or_allowed': '검토 완료 또는 허용',
      'final_confirmation_required': '최종 확인 필요',
      'kill_switch_off': '킬 스위치 꺼짐',
      'dry_run_off_for_live_submit': '실주문 전 dry_run 꺼짐',
      'kis_real_orders_enabled': '한국투자증권 실주문 허용',
      'market_session_allowed': '시장 세션 허용',
      'no_new_entry_window_allowed': '신규 진입 시간 허용',
      'cash_sufficient': '예수금 충분',
      'score_gate_passed': '점수 기준 통과',
      'risk_gate_passed': '리스크 기준 통과',
      'duplicate_order_block': '중복 주문 차단 확인',
      'daily_limit_check': '일일 한도 확인',
      'live_auto_buy_enabled': '보호된 실매수 활성',
      'scheduler_live_disabled': '스케줄러 실주문 비활성',
      'active_profile_allowed': '활성 프로필 허용',
      'max_positions': '최대 보유 종목 확인',
      'order_plan_quantity': '예상 수량 확인',
      'position_exists': '보유 포지션 존재',
      'available_quantity_positive': '매도 가능 수량',
      'requested_quantity_valid': '요청 수량 확인',
      'broker_read_available': '브로커 조회 가능',
      'cost_basis_available': '평균 매수금액 확인',
      'pl_calculation_safe': '손익 계산 안전',
      'duplicate_sell_order_check': '중복 매도 주문 확인',
      'open_order_conflict_check': '미체결 주문 충돌 확인',
      'stop_loss_or_take_profit_context': '손절/익절 조건',
      'manual_review_required': '수동 검토 필요',
      'account_snapshot': '계좌 조회',
    };
    final guardedSellKo = <String, String>{
      'final_confirmation_received': '理쒖쥌 ?뺤씤 ?꾨즺',
      'dry_run_allows_live_submit': 'dry_run ?ㅼ＜臾??덉슜',
      'broker_submit_ready': '釉뚮줈而??쒖텧 以鍮?',
      'manual_review_complete': '?섎룞 寃???꾨즺',
    };
    if (isKorean) {
      return guardedSellKo[normalized] ??
          ko[normalized] ??
          normalized.replaceAll('_', ' ');
    }
    return normalized.replaceAll('_', ' ').toUpperCase();
  }

  String preflightChecklistStatus(String status) {
    final normalized = status.trim().toLowerCase();
    if (isKorean) {
      if (normalized == 'pass') return '통과';
      if (normalized == 'warn') return '주의';
      if (normalized == 'fail') return '실패';
    }
    return normalized.toUpperCase();
  }

  List<String> get schedulerSafetyBadges => [
        dryRunOnly,
        promotionQueueOnly,
        noLiveOrders,
        schedulerRealOrdersDisabled,
        noValidationInScheduler,
        noBrokerSubmitInScheduler,
      ];

  List<String> get promotionSafetyBadges => [
        promotionOnly,
        reviewRequired,
        notAnOrder,
        noBrokerSubmit,
        liveConversionRequiresFinalConfirmation,
        schedulerRealOrdersDisabled,
      ];

  List<String> get autoBuyOperationsBadges => [
        autoBuyOps,
        dryRunEvidenceRequired,
        targetRiskGated,
        kisValidationRequired,
        oneShotLiveBuy,
        scheduledDryRun,
        promotionOnly,
        noLiveScheduler,
        noAutoRetry,
      ];

  List<String> get autoBuyPhase1Badges => [
        disabledByDefault,
        maxOnePerDay,
        positionsFirst,
        readinessRequired,
        noLiveScheduler,
        noAutoRetryTitle,
      ];

  List<String> get autoSellPhase1Badges => [
        disabledByDefault,
        maxOnePerDay,
        heldPositionsOnly,
        riskReductionOnly,
        readinessRequired,
        noAutoRetryTitle,
      ];

  List<String> get portfolioOrchestratorBadges => [
        positionsFirst,
        disabledByDefault,
        noAutoRetryTitle,
      ];

  String brokerName(String value) {
    return brokerFullDisplayName(value);
  }

  String brokerDisplayName(String value) {
    return brokerFullDisplayName(value);
  }

  String brokerCompactDisplayName(String value) {
    final normalized = value.trim().toLowerCase();
    if (normalized == 'kis' ||
        normalized == 'korea investment' ||
        normalized == '한국투자' ||
        normalized == '한국투자증권') {
      return kisBrokerCompact;
    }
    if (normalized == 'alpaca' || normalized == '알파카') {
      return alpacaBrokerCompact;
    }
    return value;
  }

  String brokerFullDisplayName(String value) {
    final normalized = value.trim().toLowerCase();
    if (normalized == 'kis' ||
        normalized == 'korea investment' ||
        normalized == '한국투자' ||
        normalized == '한국투자증권') {
      return kisBroker;
    }
    if (normalized == 'alpaca' || normalized == '알파카') {
      return alpacaBroker;
    }
    return value;
  }

  String lifecycleEventLabel(String value) {
    final normalized = value.trim().toLowerCase();
    final ko = <String, String>{
      'promotion_created': '?꾨낫 ?앹꽦',
      'promotion_reviewed': '?꾨낫 寃??',
      'buy_preflight': '留ㅼ닔 ?ъ쟾 ?먭?',
      'guarded_buy_submitted': '吏꾩엯 二쇰Ц ?쒖텧',
      'buy_filled': '吏꾩엯 泥닿껐',
      'position_opened': '蹂댁쑀 ?쒖옉',
      'sell_preflight': '留ㅻ룄 ?ъ쟾 ?먭?',
      'guarded_sell_submitted': '泥?궛 二쇰Ц ?쒖텧',
      'sell_filled': '泥?궛 泥닿껐',
      'position_closed': '蹂댁쑀 醫낅즺',
      'sync_update': '?숆린??媛깆떊',
      'blocked': '李⑤떒??',
      'unknown': '?뚯씤 遺덇?',
    };
    final en = <String, String>{
      'promotion_created': 'Promotion Created',
      'promotion_reviewed': 'Promotion Reviewed',
      'buy_preflight': 'Buy Preflight',
      'guarded_buy_submitted': 'Guarded Buy Submitted',
      'buy_filled': 'Buy Filled',
      'position_opened': 'Position Opened',
      'sell_preflight': 'Sell Preflight',
      'guarded_sell_submitted': 'Guarded Sell Submitted',
      'sell_filled': 'Sell Filled',
      'position_closed': 'Position Closed',
      'sync_update': 'Sync Update',
      'blocked': 'Blocked',
      'unknown': 'Unknown',
    };
    return isKorean
        ? (ko[normalized] ?? normalized.replaceAll('_', ' '))
        : (en[normalized] ?? normalized.replaceAll('_', ' '));
  }

  String statusLabel(String value) {
    final normalized = value.trim().toLowerCase();
    if (normalized.isEmpty) return '-';
    final ko = <String, String>{
      'pending': '대기 중',
      'pending_confirmation': '확인 대기',
      'review_required': '검토 필요',
      'allowed': '전환 가능',
      'reviewed': '검토 완료',
      'acknowledged': '확인됨',
      'dismissed': '제외됨',
      'converted': '실거래 전환됨',
      'expired': '만료됨',
      'stale': '오래된 후보',
      'blocked': '차단됨',
      'skipped': '건너뜀',
      'submitted': '제출됨',
      'dry_run_blocked': '드라이런 차단',
      'filled': '체결됨',
      'partially_filled': '부분 체결됨',
      'rejected': '거절됨',
      'sync_required': '동기화 필요',
      'pending_sync': '동기화 필요',
      'production_ready': '운영 준비 완료',
      'warning': '주의',
      'error': '오류',
      'would_buy': '매수 후보',
      'hold': '보류',
      'ready': '준비됨',
      'ready_for_operator_confirm': '운영자 확인 준비',
      'submitted_today': '오늘 제출됨',
      'dry_run_simulated': '드라이런 시뮬레이션',
      'completed_no_action': '실행 없음으로 완료',
      'dry_run_completed': '드라이런 완료',
      'sell_submitted': '매도 실행됨',
      'buy_submitted': '매수 실행됨',
      'auto_sell_phase1': '자동매도 1단계',
      'auto_buy_phase1': '자동매수 1단계',
      'none': '없음',
      'buy': '매수',
      'sell': '매도',
      'enabled': '활성',
      'disabled': '비활성',
    };
    if (isKorean) {
      return ko[normalized] ?? normalized.replaceAll('_', ' ');
    }
    return normalized.replaceAll('_', ' ').toUpperCase();
  }

  String booleanLabel(bool value) => value ? yes : no;
}

String _automationFallbackLabel(String value) {
  final words = value
      .replaceAll('_', ' ')
      .split(' ')
      .where((word) => word.trim().isNotEmpty);
  return words
      .map((word) => word.length <= 1
          ? word.toUpperCase()
          : '${word[0].toUpperCase()}${word.substring(1)}')
      .join(' ');
}
