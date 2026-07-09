import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/i18n/app_strings.dart';

void main() {
  test('AppLanguage defaults unknown values to Korean', () {
    expect(appLanguageFromCode(null), AppLanguage.korean);
    expect(appLanguageFromCode('ko-KR'), AppLanguage.korean);
    expect(appLanguageFromCode('en-US'), AppLanguage.english);
  });

  test('AppStrings maps brokers and statuses by language', () {
    final ko = AppStrings(AppLanguage.korean);
    final en = AppStrings(AppLanguage.english);

    expect(ko.brokerName('kis'), '한국투자증권');
    expect(ko.brokerName('alpaca'), '알파카');
    expect(ko.brokerDisplayName('kis'), '한국투자증권');
    expect(ko.brokerCompactDisplayName('kis'), '한국투자');
    expect(ko.brokerFullDisplayName('kis'), '한국투자증권');
    expect(ko.brokerCompactDisplayName('alpaca'), '알파카');
    expect(en.brokerName('kis'), 'KIS');
    expect(en.brokerName('alpaca'), 'Alpaca');
    expect(en.brokerDisplayName('kis'), 'KIS');
    expect(en.brokerCompactDisplayName('kis'), 'KIS');
    expect(en.brokerFullDisplayName('alpaca'), 'Alpaca');
    expect(ko.statusLabel('sync_required'), '동기화 필요');
    expect(ko.statusLabel('review_required'), '검토 필요');
    expect(en.statusLabel('sync_required'), 'SYNC REQUIRED');
    expect(en.statusLabel('review_required'), 'REVIEW REQUIRED');
    expect(ko.preflightLiveBuy, '매수 전환 사전 점검');
    expect(ko.noLiveOrderSubmitted, '실주문 없음');
    expect(en.preflightLiveBuy, 'Preflight Live Buy');
    expect(en.noLiveOrderSubmitted, 'No Live Order Submitted');
    expect(ko.positionExitReview, '포지션 청산 검토');
    expect(ko.sellPreflight, '매도 사전 점검');
    expect(ko.noBrokerSubmitDisplay, '브로커 제출 없음');
    expect(en.positionExitReview, 'Position Exit Review');
    expect(en.sellPreflight, 'Sell Preflight');
    expect(en.noBrokerSubmitDisplay, 'No Broker Submit');
    expect(en.operatorAlertCenter, 'Operator Alert Center');
    expect(en.riskAlerts, 'Risk Alerts');
    expect(en.rejectedOrder, 'Rejected Order');
    expect(en.autoExitCandidates, 'Auto Exit Candidates');
    expect(en.positionMonitoring, 'Position Monitoring');
    expect(en.stopLossCandidate, 'Stop-Loss Candidate');
    expect(en.takeProfitCandidate, 'Take-Profit Candidate');
    expect(en.trendBreakdown, 'Trend Breakdown');
    expect(en.weakMomentum, 'Weak Momentum');
    expect(en.nearCloseRisk, 'Near-Close Risk');
    expect(en.duplicateSellOrder, 'Duplicate Sell Order');
    expect(en.manualReviewRequired, 'Manual Review Required');
    expect(en.refreshExitCandidates, 'Refresh Exit Candidates');
    expect(en.autoExitCandidateTypeLabel('sync_required'), 'Sync Required');
    expect(en.positionManagementDryRun, 'Position Management Dry-Run');
    expect(en.positionsFirst, 'Positions First');
    expect(en.autoBuyPhase1, 'Auto Buy Phase 1');
    expect(en.limitedLiveAutoBuy, 'Limited Live Auto Buy');
    expect(en.disabledByDefault, 'Disabled by Default');
    expect(en.maxOnePerDay, 'Max 1 Per Day');
    expect(en.readinessRequired, 'Readiness Required');
    expect(en.refreshAutoBuyPhase1Status, 'Refresh Phase 1 Status');
    expect(en.runPhase1AttemptOnce, 'Run Phase 1 Once');
    expect(en.autoBuyPhase1Badges, contains(en.noAutoRetryTitle));
    expect(en.autoExitCandidateCheck, 'Auto Exit Candidate Check');
    expect(en.dryRunOnly, 'DRY-RUN ONLY');
    expect(en.noSellExecution, 'No Sell Execution');
    expect(en.positionsChecked, 'Positions Checked');
    expect(en.exitCandidates, 'Exit Candidates');
    expect(en.criticalCandidates, 'Critical Candidates');
    expect(en.runPositionManagementDryRunOnce,
        'Run Position Management Dry-Run Once');
    expect(en.operatorReadOnly, 'Read Only');
    expect(en.operatorNoLiveOrders, 'No Live Orders');
    expect(ko.productionReadiness, '운영 준비 점검');
    expect(ko.liveReadinessStatus, '실전 준비 상태');
    expect(ko.readinessBlocked, '차단됨');
    expect(ko.automationUnlockNotAllowed, '자동화 해제 불가');
    expect(en.productionReadiness, 'Production Readiness');
    expect(en.liveReadinessStatus, 'Live Readiness Status');
    expect(en.readinessReady, 'Ready');
    expect(en.readinessWarning, 'Warning');
    expect(en.readinessBlocked, 'Blocked');
    expect(en.readinessUnknown, 'Unknown');
    expect(en.readinessStatusLabel('blocked'), 'Blocked');
    expect(en.productionReadinessRefreshInProgress,
        'Production readiness refresh already in progress.');
    expect(en.productionReadinessStatus('Blocked'),
        'Production readiness: Blocked.');
    expect(en.primaryBlockReasons, 'Primary Block Reasons');
    expect(en.nextSafeActions, 'Next Safe Actions');
    expect(en.runtimeSettings, 'Runtime Settings');
    expect(en.brokerStatus, 'Broker Status');
    expect(en.schedulerSafety, 'Scheduler Safety');
    expect(en.orderReconciliation, 'Order Reconciliation');
    expect(en.positionsPnl, 'Positions / P&L');
    expect(en.alertStatus, 'Alert Status');
    expect(en.agentChatSafety, 'Agent Chat Safety');
    expect(en.guardedBuy, 'Guarded Buy');
    expect(en.guardedSell, 'Guarded Sell');
    expect(en.databaseStatus, 'Database');
    expect(en.automationUnlockNotAllowed, 'Automation Unlock Not Allowed');
    expect(ko.readinessStatusLabel('blocked'), ko.readinessBlocked);
    expect(ko.operatorAlertCenter, isNotEmpty);
    expect(ko.riskAlerts, isNotEmpty);
    expect(ko.autoExitCandidates, isNotEmpty);
    expect(ko.positionMonitoring, isNotEmpty);
    expect(ko.positionManagementDryRun, isNotEmpty);
    expect(ko.positionsFirst, isNotEmpty);
  });
}
