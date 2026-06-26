import 'package:flutter/material.dart';

import '../../core/utils/timestamp_formatter.dart';
import '../../core/widgets/section_card.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/agent_chat_message.dart';
import '../../models/automation_runtime_monitor.dart';
import '../../models/log_items.dart';
import '../../models/portfolio_summary.dart';
import '../../models/scheduler_status.dart';
import '../../models/trading_run.dart';
import 'dashboard_controller.dart';
import 'widgets/agent_operations_summary_card.dart';
import 'widgets/agent_chat_live_auto_buy_status_card.dart';
import 'widgets/agent_chat_live_auto_exit_status_card.dart';
import 'widgets/automation_event_timeline_card.dart';
import 'widgets/automation_runtime_monitor_card.dart';
import 'widgets/agent_chat_full_panel.dart';
import 'widgets/agent_chat_panel.dart';
import 'widgets/agent_review_queue_panel.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/operation_rehearsal_panel.dart';
import 'widgets/portfolio_snapshot_section.dart';
import 'widgets/strategy_profile_card.dart';
import 'widgets/strategy_daily_pnl_card.dart';
import 'widgets/strategy_monthly_progress_card.dart';
import 'widgets/strategy_risk_state_card.dart';
import 'widgets/strategy_dry_run_auto_buy_card.dart';
import 'widgets/strategy_live_auto_buy_card.dart';
import 'widgets/strategy_live_auto_exit_card.dart';
import 'widgets/strategy_trade_performance_list.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
    this.onReviewPosition,
    this.onOpenLogs,
    this.onOpenSettings,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;
  final VoidCallback? onOpenLogs;
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: Stack(
            children: [
              RefreshIndicator(
                onRefresh: controller.load,
                child: ListView(
                  key: const Key('dashboard_home_scroll_view'),
                  padding: const EdgeInsets.all(16),
                  children: [
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Expanded(
                          child: Text(
                            'Home',
                            style: TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        GlobalBrokerSelector(controller: controller),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      controller.selectedProvider == SelectedProvider.kis
                          ? 'KIS account, manual live safety, and recent KR activity.'
                          : 'Alpaca paper portfolio, watchlist status, and recent US activity.',
                      style: const TextStyle(color: Colors.white70),
                    ),
                    const SizedBox(height: 14),
                    AgentChatPanel(
                      controller: controller,
                      onOpenManualOrder: onOpenManualOrder,
                    ),
                    const SizedBox(height: 12),
                    _CompactSafetyStatusBar(
                      controller: controller,
                      onOpenSettings: onOpenSettings,
                    ),
                    const SizedBox(height: 12),
                    _CompactPortfolioSummaryCard(
                      controller: controller,
                      onOpenManualOrder: onOpenManualOrder,
                      onOpenLogs: onOpenLogs,
                    ),
                    const SizedBox(height: 12),
                    _RecentTradesCompactCard(
                      controller: controller,
                      onOpenLogs: onOpenLogs,
                    ),
                    const SizedBox(height: 12),
                    _HomeAdvancedDetailsSection(
                      controller: controller,
                      onOpenManualOrder: onOpenManualOrder,
                      onReviewPosition: onReviewPosition,
                      onOpenSettings: onOpenSettings,
                    ),
                    if (controller.error != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        controller.error!,
                        style: const TextStyle(color: Colors.orangeAccent),
                      ),
                    ],
                  ],
                ),
              ),
              if (controller.agentChatMode == AgentChatPanelMode.fullscreen)
                Positioned.fill(
                  child: AgentChatFullPanel(
                    controller: controller,
                    onOpenManualOrder: onOpenManualOrder,
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _CompactSafetyStatusBar extends StatelessWidget {
  const _CompactSafetyStatusBar({
    required this.controller,
    required this.onOpenSettings,
  });

  final DashboardController controller;
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final safety = controller.kisSafetyStatus;
    final scheduler = controller.schedulerStatus;
    final liveBuyArmed = settings.kisLiveAutoBuyEnabled ||
        scheduler.liveBuyPossible ||
        scheduler.kr.liveBuyArmed;
    final liveSellArmed = settings.kisLiveAutoSellEnabled ||
        scheduler.liveSellPossible ||
        scheduler.kr.liveSellArmed;
    final realOrdersAllowed =
        safety.kisRealOrderEnabled || scheduler.kr.realOrdersAllowed;
    final marketOpen = controller.isKisSelected
        ? safety.marketOpen
        : scheduler.us.enabledForScheduler;

    return SectionCard(
      key: const Key('home_compact_safety_status_bar'),
      padding: const EdgeInsets.all(14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Icon(Icons.shield_outlined, size: 20),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Safety Status',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                _SafetyPill(
                  text: controller.isKisSelected
                      ? 'BROKER KIS'
                      : 'BROKER ALPACA',
                  color: Colors.lightBlueAccent,
                ),
                _SafetyPill(
                  text: settings.dryRun ? 'DRY RUN ON' : 'DRY RUN OFF',
                  color:
                      settings.dryRun ? Colors.amberAccent : Colors.redAccent,
                ),
                _SafetyPill(
                  text: settings.killSwitch
                      ? 'KILL SWITCH ON'
                      : 'KILL SWITCH OFF',
                  color: settings.killSwitch
                      ? Colors.redAccent
                      : Colors.greenAccent,
                ),
                _SafetyPill(
                  text:
                      realOrdersAllowed ? 'REAL ORDERS ON' : 'REAL ORDERS OFF',
                  color: realOrdersAllowed
                      ? Colors.redAccent
                      : Colors.greenAccent,
                ),
                _SafetyPill(
                  text: marketOpen ? 'MARKET OPEN' : 'MARKET CLOSED',
                  color: marketOpen ? Colors.greenAccent : Colors.white70,
                ),
                _SafetyPill(
                  text: liveBuyArmed ? 'BUY AUTO ON' : 'BUY AUTO OFF',
                  color:
                      liveBuyArmed ? Colors.redAccent : Colors.greenAccent,
                ),
                _SafetyPill(
                  text: liveSellArmed ? 'SELL AUTO ON' : 'SELL AUTO OFF',
                  color:
                      liveSellArmed ? Colors.orangeAccent : Colors.greenAccent,
                ),
              ]),
            ],
          ),
        ),
        IconButton(
          key: const ValueKey('home-open-safety-settings'),
          tooltip: 'Open safety settings',
          onPressed: onOpenSettings,
          icon: const Icon(Icons.settings_outlined, size: 20),
        ),
      ]),
    );
  }
}

class _CompactPortfolioSummaryCard extends StatelessWidget {
  const _CompactPortfolioSummaryCard({
    required this.controller,
    required this.onOpenManualOrder,
    required this.onOpenLogs,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onOpenLogs;

  @override
  Widget build(BuildContext context) {
    final summary = controller.isKisSelected
        ? controller.krPortfolioSummary
        : controller.usPortfolioSummary;
    final market = controller.isKisSelected ? 'KR' : 'US';
    final totalAssets =
        summary.totalMarketValue + (summary.cashKnown ? summary.cash : 0);
    final unavailable = controller.isKisSelected &&
        (controller.krPortfolioUnavailable || summary.hasUnavailableKisData);

    return SectionCard(
      key: const Key('home_compact_portfolio_summary_card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.account_balance_wallet_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Portfolio Summary',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                unavailable
                    ? '$market account data is partially unavailable.'
                    : '$market ${summary.positionsCount} holdings, ${summary.pendingOrdersCount} pending orders',
                style: const TextStyle(color: Colors.white70),
              ),
            ]),
          ),
          if (onOpenManualOrder != null)
            IconButton(
              key: const ValueKey('home-open-trading'),
              tooltip: 'Open trading',
              onPressed: onOpenManualOrder,
              icon: const Icon(Icons.swap_horiz_outlined, size: 20),
            ),
          IconButton(
            key: const ValueKey('home-portfolio-view-logs'),
            tooltip: 'View all logs',
            onPressed: onOpenLogs,
            icon: const Icon(Icons.receipt_long_outlined, size: 20),
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 10, children: [
          _CompactMetric(
            label: 'Assets',
            value: _formatMoney(summary.currency, totalAssets),
          ),
          _CompactMetric(
            label: 'Cash',
            value: summary.cashKnown
                ? _formatMoney(summary.currency, summary.cash)
                : 'Unknown',
          ),
          _CompactMetric(
            label: 'P&L',
            value: _formatSignedMoney(
              summary.currency,
              summary.totalUnrealizedPl,
            ),
            color: summary.totalUnrealizedPl >= 0
                ? Colors.greenAccent
                : Colors.redAccent,
          ),
          _CompactMetric(
            label: 'P&L %',
            value: _formatPercent(summary.totalUnrealizedPlpc),
            color: summary.totalUnrealizedPl >= 0
                ? Colors.greenAccent
                : Colors.redAccent,
          ),
        ]),
      ]),
    );
  }
}

class _RecentTradesCompactCard extends StatelessWidget {
  const _RecentTradesCompactCard({
    required this.controller,
    required this.onOpenLogs,
  });

  final DashboardController controller;
  final VoidCallback? onOpenLogs;

  @override
  Widget build(BuildContext context) {
    final orders = controller.automationRecentOrders.take(3).toList();
    final runs = controller.recentRuns.take(3).toList();
    final hasOrders = orders.isNotEmpty;
    final count = hasOrders ? orders.length : runs.length;

    return SectionCard(
      key: const Key('home_recent_trades_compact_card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.history_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Recent Trades / Last Activity',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                count == 0
                    ? 'No recent activity loaded.'
                    : 'Latest $count shown',
                style: const TextStyle(color: Colors.white70),
              ),
            ]),
          ),
          TextButton.icon(
            key: const ValueKey('home-view-all-logs'),
            onPressed: onOpenLogs,
            icon: const Icon(Icons.open_in_new, size: 16),
            label: const Text('View all logs'),
          ),
        ]),
        const SizedBox(height: 10),
        if (count == 0)
          const Text('No recent trades yet.',
              style: TextStyle(color: Colors.white70))
        else if (hasOrders)
          for (var i = 0; i < orders.length; i++)
            _CompactRecentLine(
              key: ValueKey('home-recent-compact-item-$i'),
              title:
                  '${orders[i].side.toUpperCase()} ${orders[i].symbol} - ${orders[i].statusLabel}',
              subtitle: _recentOrderSubtitle(orders[i]),
              badge: orders[i].sourceLabel,
            )
        else
          for (var i = 0; i < runs.length; i++)
            _CompactRecentLine(
              key: ValueKey('home-recent-compact-item-$i'),
              title:
                  '${runs[i].action.isEmpty ? 'HOLD' : runs[i].action.toUpperCase()} ${runs[i].symbol}',
              subtitle: _recentRunSubtitle(runs[i]),
              badge: runs[i].triggerSource,
            ),
      ]),
    );
  }
}

class _HomeAdvancedDetailsSection extends StatelessWidget {
  const _HomeAdvancedDetailsSection({
    required this.controller,
    required this.onOpenManualOrder,
    required this.onReviewPosition,
    required this.onOpenSettings,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('home_advanced_details_section'),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          key: const ValueKey('home-advanced-details-toggle'),
          tilePadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
          childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          leading: const Icon(Icons.tune_outlined, size: 20),
          title: const Text(
            'Advanced Details',
            style: TextStyle(fontWeight: FontWeight.w800),
          ),
          children: [
            _OperationalReadinessCard(
              controller: controller,
              onOpenSettings: onOpenSettings,
            ),
            const SizedBox(height: 12),
            StrategyProfileCard(
              profiles: controller.strategyProfiles,
              activeProfile: controller.activeStrategyProfile,
              loading: controller.strategyProfilesLoading,
              error: controller.strategyProfileError,
              applyingProfileName: controller.applyingStrategyProfileName,
              onRefresh: controller.refreshStrategyProfiles,
              onApply: controller.applyStrategyProfilePreset,
            ),
            const SizedBox(height: 12),
            StrategyRiskStateCard(
              riskState: controller.strategyRiskState,
              loading: controller.strategyRiskLoading,
              error: controller.strategyRiskError,
              onRefresh: controller.refreshStrategyRiskState,
            ),
            const SizedBox(height: 12),
            StrategyDryRunAutoBuyCard(
              result: controller.strategyDryRunAutoBuyResult,
              loading: controller.strategyDryRunAutoBuyLoading,
              error: controller.strategyDryRunAutoBuyError,
              onRun: controller.runStrategyDryRunAutoBuy,
              onRefresh: controller.refreshStrategyDryRunAutoBuy,
            ),
            const SizedBox(height: 12),
            StrategyLiveAutoBuyCard(
              readiness: controller.strategyLiveAutoBuyReadiness,
              latest: controller.strategyLiveAutoBuyResult,
              recent: controller.strategyLiveAutoBuyRecent,
              loading: controller.strategyLiveAutoBuyLoading,
              error: controller.strategyLiveAutoBuyError,
              onRun: controller.runStrategyLiveAutoBuyOnce,
              onRefresh: controller.refreshStrategyLiveAutoBuy,
            ),
            const SizedBox(height: 12),
            AgentChatLiveAutoBuyStatusCard(
              readiness: controller.strategyLiveAutoBuyReadiness,
              recent: controller.strategyLiveAutoBuyRecent,
              loading: controller.strategyLiveAutoBuyLoading,
              error: controller.strategyLiveAutoBuyError,
              onRefresh: controller.refreshStrategyLiveAutoBuy,
            ),
            const SizedBox(height: 12),
            StrategyLiveAutoExitCard(
              readiness: controller.strategyLiveAutoExitReadiness,
              latest: controller.strategyLiveAutoExitResult,
              recent: controller.strategyLiveAutoExitRecent,
              loading: controller.strategyLiveAutoExitLoading,
              error: controller.strategyLiveAutoExitError,
              onRun: controller.runStrategyLiveAutoExitOnce,
              onRefresh: controller.refreshStrategyLiveAutoExit,
            ),
            const SizedBox(height: 12),
            AgentChatLiveAutoExitStatusCard(
              readiness: controller.strategyLiveAutoExitReadiness,
              recent: controller.strategyLiveAutoExitRecent,
              loading: controller.strategyLiveAutoExitLoading,
              error: controller.strategyLiveAutoExitError,
              onRefresh: controller.refreshStrategyLiveAutoExit,
            ),
            const SizedBox(height: 12),
            StrategyMonthlyProgressCard(
              performance: controller.strategyMonthlyPerformance,
              loading: controller.strategyPerformanceLoading,
              error: controller.strategyPerformanceError,
              onRefresh: controller.refreshStrategyPerformance,
            ),
            const SizedBox(height: 12),
            StrategyDailyPnlCard(
              performance: controller.strategyDailyPerformance,
              loading: controller.strategyPerformanceLoading,
              error: controller.strategyPerformanceError,
            ),
            const SizedBox(height: 12),
            StrategyTradePerformanceListCard(
              performance: controller.strategyTradePerformance,
              loading: controller.strategyPerformanceLoading,
            ),
            const SizedBox(height: 12),
            AgentOperationsSummaryCard(controller: controller),
            const SizedBox(height: 12),
            AgentReviewQueuePanel(controller: controller),
            const SizedBox(height: 12),
            _PreLiveOperationsCard(
              controller: controller,
              onOpenManualOrder: onOpenManualOrder,
            ),
            const SizedBox(height: 12),
            _SafetySummary(controller: controller),
            const SizedBox(height: 12),
            AutomationRuntimeMonitorCard(controller: controller),
            const SizedBox(height: 12),
            OperationRehearsalPanel(controller: controller),
            const SizedBox(height: 12),
            AutomationEventTimelineCard(controller: controller),
            const SizedBox(height: 12),
            PortfolioSnapshotSection(
              controller: controller,
              managementMode: true,
              onOpenManualOrder: onOpenManualOrder,
              onReviewPosition: onReviewPosition,
            ),
            const SizedBox(height: 12),
            _NextActionCard(controller: controller),
            const SizedBox(height: 12),
            _RecentActivityCard(controller: controller),
          ],
        ),
      ),
    );
  }
}

class _CompactMetric extends StatelessWidget {
  const _CompactMetric({
    required this.label,
    required this.value,
    this.color,
  });

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 118),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: const TextStyle(color: Colors.white54, fontSize: 12)),
        const SizedBox(height: 3),
        Text(
          value,
          style: TextStyle(
            color: color ?? Colors.white,
            fontWeight: FontWeight.w800,
          ),
        ),
      ]),
    );
  }
}

class _CompactRecentLine extends StatelessWidget {
  const _CompactRecentLine({
    super.key,
    required this.title,
    required this.subtitle,
    required this.badge,
  });

  final String title;
  final String subtitle;
  final String badge;

  @override
  Widget build(BuildContext context) {
    final badgeText = badge.trim().isEmpty ? 'activity' : badge.trim();
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800)),
            const SizedBox(height: 3),
            Text(
              subtitle,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white70),
            ),
          ]),
        ),
        const SizedBox(width: 8),
        _SafetyPill(text: badgeText.toUpperCase(), color: Colors.white70),
      ]),
    );
  }
}

class _PreLiveOperationsCard extends StatelessWidget {
  const _PreLiveOperationsCard({
    required this.controller,
    required this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  Widget build(BuildContext context) {
    final summary = controller.krPortfolioSummary;
    final managementItems =
        controller.portfolioManagementItemsForMarket(PortfolioMarket.kr);
    final exitReviewCount = managementItems
        .where((item) =>
            item.manualSellAvailable &&
            item.triggerStatus != TriggerStatus.hold &&
            item.triggerStatus != TriggerStatus.noData)
        .length;
    final preflight = controller.kisLiveExitPreflightResult;
    final preparedSellTicket = controller.hasPreparedKisManualSellTicket;
    final validation = controller.orderValidationResult;
    final validationCurrent =
        validation != null && controller.orderValidationMatchesCurrent;
    final validationReady = validationCurrent &&
        validation.validatedForSubmission &&
        !controller.orderValidationExpired;
    final schedulerRealOrdersOn =
        controller.schedulerStatus.kr.realOrderSchedulerEnabled ||
            controller.schedulerStatus.kr.realOrdersAllowed ||
            controller.settings.kisSchedulerAllowRealOrders;
    final liveAutoBuyOn = controller.settings.kisLiveAutoBuyEnabled ||
        controller.schedulerStatus.kr.liveBuyArmed ||
        controller.schedulerStatus.liveBuyPossible;

    return SectionCard(
      key: const Key('pre_live_operations_card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.assignment_turned_in_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                'Pre-Live Operations',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              Text(
                _preLiveSummary(
                  summary: summary,
                  exitReviewCount: exitReviewCount,
                  preflightCandidateCount: preflight?.candidateCount,
                  preparedSellTicket: preparedSellTicket,
                ),
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
            ]),
          ),
          _ReadinessBadge(
            text: preparedSellTicket ? 'TICKET READY' : 'REVIEW MODE',
            color: preparedSellTicket
                ? Colors.greenAccent
                : Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _ReadinessBadge(
            text: 'PREFLIGHT FIRST',
            color: Colors.lightBlueAccent,
          ),
          const _ReadinessBadge(
            text: 'TICKET PREFILL ONLY',
            color: Colors.greenAccent,
          ),
          const _ReadinessBadge(
            text: 'VALIDATION REQUIRED',
            color: Colors.lightBlueAccent,
          ),
          const _ReadinessBadge(
            text: 'CONFIRM_LIVE MANUAL',
            color: Colors.redAccent,
          ),
          _ReadinessBadge(
            text: liveAutoBuyOn ? 'LIVE AUTO BUY ON' : 'LIVE AUTO BUY OFF',
            color: liveAutoBuyOn ? Colors.redAccent : Colors.greenAccent,
          ),
          _ReadinessBadge(
            text: schedulerRealOrdersOn
                ? 'SCHEDULER REAL ORDERS ON'
                : 'SCHEDULER REAL ORDERS OFF',
            color:
                schedulerRealOrdersOn ? Colors.redAccent : Colors.greenAccent,
          ),
        ]),
        const SizedBox(height: 14),
        LayoutBuilder(builder: (context, constraints) {
          final steps = [
            _PreLiveStep(
              label: 'Holdings',
              value: _preLiveHoldingsLabel(summary),
              color: summary.positionsUnavailable
                  ? Colors.amberAccent
                  : summary.positions.isEmpty
                      ? Colors.white70
                      : Colors.greenAccent,
            ),
            _PreLiveStep(
              label: 'Exit preflight',
              value: preflight == null
                  ? 'not run'
                  : '${preflight.action} / ${preflight.candidateCount}',
              color: preflight == null
                  ? Colors.white70
                  : preflight.candidateCount > 0
                      ? Colors.greenAccent
                      : Colors.lightBlueAccent,
            ),
            _PreLiveStep(
              label: 'Manual ticket',
              value: preparedSellTicket ? 'prefilled' : 'not prepared',
              color: preparedSellTicket ? Colors.greenAccent : Colors.white70,
            ),
            _PreLiveStep(
              label: 'Validation',
              value: _preLiveValidationLabel(
                validation: validation,
                validationReady: validationReady,
                validationCurrent: validationCurrent,
              ),
              color: _preLiveValidationColor(
                validation: validation,
                validationReady: validationReady,
                validationCurrent: validationCurrent,
              ),
            ),
            _PreLiveStep(
              label: 'confirm_live',
              value: controller.kisLiveConfirmation ? 'checked' : 'manual',
              color: controller.kisLiveConfirmation
                  ? Colors.redAccent
                  : Colors.white70,
            ),
            _PreLiveStep(
              label: 'Submit',
              value: controller.canSubmitLiveKisOrder ? 'available' : 'blocked',
              color: controller.canSubmitLiveKisOrder
                  ? Colors.redAccent
                  : Colors.white70,
            ),
          ];
          if (constraints.maxWidth >= 760) {
            return Row(children: [
              for (var i = 0; i < steps.length; i++) ...[
                if (i > 0) const SizedBox(width: 8),
                Expanded(child: steps[i]),
              ],
            ]);
          }
          return Wrap(spacing: 8, runSpacing: 8, children: steps);
        }),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: const ValueKey('pre-live-refresh-positions'),
            onPressed: controller.portfolioManagementLoading
                ? null
                : () => _refreshPositions(context),
            icon: controller.portfolioManagementLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh, size: 16),
            label: const Text('Refresh Positions'),
          ),
          FilledButton.icon(
            key: const ValueKey('pre-live-run-exit-preflight'),
            onPressed: controller.kisLiveExitPreflightLoading
                ? null
                : () => _runExitPreflight(context),
            icon: controller.kisLiveExitPreflightLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.fact_check_outlined, size: 16),
            label: Text(controller.kisLiveExitPreflightLoading
                ? 'Running Exit Preflight...'
                : 'Run Exit Preflight'),
          ),
          if (preparedSellTicket && onOpenManualOrder != null)
            OutlinedButton.icon(
              key: const ValueKey('pre-live-open-manual-ticket'),
              onPressed: onOpenManualOrder,
              icon: const Icon(Icons.open_in_new, size: 16),
              label: const Text('Open Manual Ticket'),
            ),
        ]),
        if (controller.kisLiveExitPreflightError != null) ...[
          const SizedBox(height: 10),
          Text(
            controller.kisLiveExitPreflightError!,
            style: const TextStyle(color: Colors.redAccent),
          ),
        ],
        if (controller.portfolioManagementError != null) ...[
          const SizedBox(height: 10),
          Text(
            controller.portfolioManagementError!,
            style: const TextStyle(color: Colors.orangeAccent),
          ),
        ],
      ]),
    );
  }

  Future<void> _refreshPositions(BuildContext context) async {
    final result = await controller.refreshPortfolioManagement();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(result.message)));
  }

  Future<void> _runExitPreflight(BuildContext context) async {
    final result = await controller.runKisLiveExitPreflight();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(result.message)));
  }
}

class _PreLiveStep extends StatelessWidget {
  const _PreLiveStep({
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 112,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label.toUpperCase(),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white54,
            fontSize: 10,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 5),
        Text(
          value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
      ]),
    );
  }
}

class _OperationalReadinessCard extends StatelessWidget {
  const _OperationalReadinessCard({
    required this.controller,
    required this.onOpenSettings,
  });

  final DashboardController controller;
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    final status = controller.schedulerStatus;
    final warningLevel = status.warningLevel;
    final warningColor = _warningColor(warningLevel);
    final unavailable = controller.schedulerStatusError != null;
    final showDetails = !unavailable || controller.schedulerStatusLoaded;
    final secondaryBadges = _readinessBadges(status);

    return SectionCard(
      key: const Key('operational-readiness-card'),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.shield_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                'Operational Readiness',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              const SizedBox(height: 4),
              Text(
                status.userFriendlySummary.isEmpty
                    ? 'Scheduler safety status is being checked.'
                    : status.userFriendlySummary,
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
            ]),
          ),
          const SizedBox(width: 8),
          _ReadinessBadge(
            text: _primaryReadinessBadge(status),
            color: warningColor,
          ),
          const SizedBox(width: 4),
          IconButton(
            key: const ValueKey('operational-readiness-refresh'),
            tooltip: 'Refresh readiness',
            icon: controller.schedulerStatusLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh, size: 20),
            onPressed: controller.schedulerStatusLoading
                ? null
                : () => _refreshReadiness(context),
          ),
        ]),
        if (unavailable) ...[
          const SizedBox(height: 12),
          _ReadinessWarningBanner(
            message: controller.schedulerStatusLoaded
                ? 'Operational readiness unavailable. Showing last known status.'
                : 'Operational readiness unavailable.',
            color: Colors.grey,
            action: TextButton.icon(
              key: const ValueKey('operational-readiness-retry'),
              onPressed: controller.schedulerStatusLoading
                  ? null
                  : () => _refreshReadiness(context),
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Retry'),
            ),
          ),
        ],
        if (showDetails) ...[
          if (secondaryBadges.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final badge in secondaryBadges)
                  _ReadinessBadge(text: badge.text, color: badge.color),
              ],
            ),
          ],
          const SizedBox(height: 14),
          _ReadinessSection(
            title: 'Current Mode',
            children: [
              _ReadinessField(
                label: 'Mode',
                value: '${status.modeLabel} (${status.currentOperationMode})',
              ),
              _ReadinessField(
                label: 'Warning',
                value: warningLevel,
                color: warningColor,
              ),
              _ReadinessField(
                label: 'Summary',
                value: status.userFriendlySummary.isEmpty
                    ? 'No summary returned.'
                    : status.userFriendlySummary,
              ),
            ],
          ),
          const SizedBox(height: 14),
          LayoutBuilder(builder: (context, constraints) {
            final sections = [
              _ReadinessSection(
                title: 'Global Safety',
                children: [
                  _ReadinessField(
                    label: 'Scheduler',
                    value: _onOff(status.global.schedulerEnabled),
                    color: _onOffColor(status.global.schedulerEnabled),
                  ),
                  _ReadinessField(
                    label: 'Dry-run',
                    value: _onOff(status.global.dryRun),
                    color: status.global.dryRun
                        ? Colors.lightBlueAccent
                        : Colors.orangeAccent,
                  ),
                  _ReadinessField(
                    label: 'Kill switch',
                    value: _onOff(status.global.killSwitch),
                    color: status.global.killSwitch
                        ? Colors.redAccent
                        : Colors.greenAccent,
                  ),
                ],
              ),
              _ReadinessSection(
                title: 'Alpaca / US',
                children: [
                  _ReadinessField(
                    label: 'Market',
                    value: 'US / Alpaca',
                  ),
                  _ReadinessField(
                    label: 'Scheduler',
                    value: _onOff(status.us.enabledForScheduler),
                    color: _onOffColor(status.us.enabledForScheduler),
                  ),
                  _ReadinessField(
                    label: 'Next run',
                    value: _formatScheduleTime(status.us, 'ET'),
                  ),
                  _ReadinessField(
                    label: 'No entry after',
                    value: _formatCutoff(status.us, 'ET'),
                  ),
                ],
              ),
              _ReadinessSection(
                title: 'KIS / KR',
                children: [
                  _ReadinessField(
                    label: 'Market',
                    value: 'KR / KIS',
                  ),
                  _ReadinessField(
                    label: 'Scheduler',
                    value: _onOff(status.kr.enabledForScheduler),
                    color: _onOffColor(status.kr.enabledForScheduler),
                  ),
                  _ReadinessField(
                    label: 'Next run',
                    value: _formatScheduleTime(status.kr, 'KST'),
                  ),
                  _ReadinessField(
                    label: 'No entry after',
                    value: _formatCutoff(status.kr, 'KST'),
                  ),
                  _ReadinessField(
                    label: 'Live buy armed',
                    value: _yesNo(_liveBuyArmed(status)),
                    color: _liveBuyArmed(status)
                        ? Colors.redAccent
                        : Colors.greenAccent,
                  ),
                  _ReadinessField(
                    label: 'Live sell armed',
                    value: _yesNo(_liveSellArmed(status)),
                    color: _liveSellArmed(status)
                        ? Colors.orangeAccent
                        : Colors.greenAccent,
                  ),
                  _ReadinessField(
                    label: 'Daily remaining',
                    value: _dailyRemaining(status),
                  ),
                ],
              ),
            ];
            if (constraints.maxWidth >= 760) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (var i = 0; i < sections.length; i++) ...[
                    if (i > 0) const SizedBox(width: 16),
                    Expanded(child: sections[i]),
                  ],
                ],
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var i = 0; i < sections.length; i++) ...[
                  if (i > 0) const SizedBox(height: 14),
                  sections[i],
                ],
              ],
            );
          }),
          const SizedBox(height: 14),
          _ReadinessWarningBanner(
            message: status.warningMessage.isEmpty
                ? 'No warning message returned.'
                : status.warningMessage,
            color: warningColor,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            key: const ValueKey('operational-open-settings'),
            onPressed: onOpenSettings,
            icon: const Icon(Icons.settings_outlined, size: 16),
            label: const Text('Open Settings'),
          ),
          if (warningLevel == 'dangerous_mixed')
            FilledButton.icon(
              key: const ValueKey('operational-switch-safe-mode'),
              onPressed: controller.kisAutomationSettingsLoading
                  ? null
                  : () => _switchToSafeMode(context),
              icon: const Icon(Icons.health_and_safety_outlined, size: 16),
              label: const Text('Switch to Safe Mode'),
            ),
        ]),
      ]),
    );
  }

  Future<void> _refreshReadiness(BuildContext context) async {
    final result = await controller.refreshSchedulerStatus();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _switchToSafeMode(BuildContext context) async {
    final result = await controller.applyOperationModePreset('safe_mode');
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _SafetySummary extends StatelessWidget {
  const _SafetySummary({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final safety = controller.kisSafetyStatus;
    final isKis = controller.selectedProvider == SelectedProvider.kis;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.health_and_safety_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isKis ? 'KIS Safety Summary' : 'Alpaca Safety Summary',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          StatusBadge(
            text: safety.killSwitch ? 'HALTED' : 'GUARDED',
            active: !safety.killSwitch,
            alert: safety.killSwitch,
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SafetyPill(
            text: isKis ? 'KIS live manual context' : 'Alpaca paper context',
            color: isKis ? Colors.redAccent : Colors.lightBlueAccent,
          ),
          _SafetyPill(
            text: settings.dryRun ? 'Dry run ON' : 'Dry run OFF',
            color: settings.dryRun ? Colors.lightBlueAccent : Colors.redAccent,
          ),
          _SafetyPill(
            text: settings.killSwitch ? 'Kill switch ON' : 'Kill switch OFF',
            color: settings.killSwitch ? Colors.redAccent : Colors.greenAccent,
          ),
          if (isKis) ...[
            _SafetyPill(
              text: safety.kisEnabled ? 'KIS enabled' : 'KIS disabled',
              color: safety.kisEnabled ? Colors.greenAccent : Colors.white70,
            ),
            _SafetyPill(
              text: safety.kisRealOrderEnabled
                  ? 'KIS real orders allowed'
                  : 'KIS real orders disabled',
              color: safety.kisRealOrderEnabled
                  ? Colors.redAccent
                  : Colors.white70,
            ),
            _SafetyPill(
              text: safety.marketOpen ? 'KR market open' : 'KR market closed',
              color: safety.marketOpen ? Colors.greenAccent : Colors.white70,
            ),
          ] else ...[
            _SafetyPill(
              text: 'Paper trading',
              color: Colors.greenAccent,
            ),
            _SafetyPill(
              text: controller.schedulerStatus.us.enabledForScheduler
                  ? 'US scheduler enabled'
                  : 'US scheduler disabled',
              color: controller.schedulerStatus.us.enabledForScheduler
                  ? Colors.greenAccent
                  : Colors.white70,
            ),
          ],
        ]),
      ]),
    );
  }
}

class _ReadinessSection extends StatelessWidget {
  const _ReadinessSection({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(
        title,
        style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w900),
      ),
      const SizedBox(height: 8),
      ...children,
    ]);
  }
}

class _ReadinessField extends StatelessWidget {
  const _ReadinessField({
    required this.label,
    required this.value,
    this.color,
  });

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 104,
          child: Text(
            label,
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: color ?? Colors.white,
              fontSize: 12,
              fontWeight: color == null ? FontWeight.w500 : FontWeight.w800,
              height: 1.2,
            ),
          ),
        ),
      ]),
    );
  }
}

class _ReadinessWarningBanner extends StatelessWidget {
  const _ReadinessWarningBanner({
    required this.message,
    required this.color,
    this.action,
  });

  final String message;
  final Color color;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
        Icon(Icons.warning_amber_outlined, color: color, size: 18),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            message,
            style: TextStyle(color: color, fontSize: 12, height: 1.25),
          ),
        ),
        if (action != null) ...[
          const SizedBox(width: 8),
          action!,
        ],
      ]),
    );
  }
}

class _ReadinessBadge extends StatelessWidget {
  const _ReadinessBadge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.42)),
      ),
      child: Text(
        text.toUpperCase(),
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _BadgeSpec {
  const _BadgeSpec(this.text, this.color);

  final String text;
  final Color color;
}

class _NextActionCard extends StatelessWidget {
  const _NextActionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final run = controller.runResult;
    final hasRun =
        controller.hasLatestRunResult || controller.showingOfflineFallback;
    final candidate = run.finalBestCandidate.isEmpty
        ? 'No candidate yet'
        : run.finalBestCandidate;
    final nextAction = _nextAction(controller);
    final block = run.triggerBlockReason.isEmpty
        ? 'No block reason'
        : run.triggerBlockReason;

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.assistant_direction_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Next Action',
                style: Theme.of(context).textTheme.titleMedium),
          ),
        ]),
        const SizedBox(height: 10),
        Text(
          hasRun
              ? nextAction
              : 'Start a watchlist scan to find the next candidate.',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        _DataLine(label: 'Top candidate', value: candidate),
        _DataLine(
            label: 'Block reason', value: block, color: Colors.orangeAccent),
      ]),
    );
  }
}

class _RecentActivityCard extends StatelessWidget {
  const _RecentActivityCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final runs = controller.recentRuns.take(3).toList(growable: false);
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.timeline_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Recent Activity',
                style: Theme.of(context).textTheme.titleMedium),
          ),
        ]),
        const SizedBox(height: 10),
        if (runs.isEmpty)
          const Text('No recent activity yet.',
              style: TextStyle(color: Colors.white70))
        else
          for (final run in runs) _ActivityLine(run: run),
      ]),
    );
  }
}

class _ActivityLine extends StatelessWidget {
  const _ActivityLine({required this.run});

  final TradingRun run;

  @override
  Widget build(BuildContext context) {
    final action = run.action.isEmpty ? 'hold' : run.action;
    final orderText =
        run.orderId == null ? 'No order submitted.' : 'Order ${run.orderId}.';
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        '${formatTimestampWithKst(run.timestamp)} - ${run.symbol}: $action. $orderText',
        style: const TextStyle(color: Colors.white70),
      ),
    );
  }
}

String _recentOrderSubtitle(OrderLogItem order) {
  final qty = order.qty == null ? 'qty -' : 'qty ${_formatNumber(order.qty!)}';
  final amount = order.notional == null
      ? ''
      : ' / ${_formatMoney(order.currency, order.notional!)}';
  return '${formatTimestampWithKst(order.createdAt)} - $qty$amount';
}

String _recentRunSubtitle(TradingRun run) {
  final reason = run.reason.trim().isEmpty ? run.result : run.reason;
  final order = run.orderId == null ? 'No order' : 'Order ${run.orderId}';
  return '${formatTimestampWithKst(run.timestamp)} - $order - $reason';
}

String _formatMoney(String currency, double value) {
  final code = currency.trim().toUpperCase();
  if (code == 'KRW') return 'KRW ${_formatWhole(value)}';
  final prefix = code == 'USD' || code.isEmpty ? '\$' : '$code ';
  return '$prefix${value.toStringAsFixed(2)}';
}

String _formatSignedMoney(String currency, double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${_formatMoney(currency, value)}';
}

String _formatPercent(double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(2)}%';
}

String _formatWhole(double value) => value.toStringAsFixed(0);

String _formatNumber(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}

class _DataLine extends StatelessWidget {
  const _DataLine({required this.label, required this.value, this.color});

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 110,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(color: color ?? Colors.white),
          ),
        ),
      ]),
    );
  }
}

class _SafetyPill extends StatelessWidget {
  const _SafetyPill({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

String _nextAction(DashboardController controller) {
  final run = controller.runResult;
  if (controller.settings.killSwitch)
    return 'Kill switch is ON. Keep trading halted.';
  if (run.finalBestCandidate.isEmpty) return 'Run a watchlist scan.';
  if (!run.finalEntryReady) return 'Review the block reason before any ticket.';
  return 'Review ${run.finalBestCandidate} in Trading before any submit.';
}

String _primaryReadinessBadge(SchedulerStatus status) {
  switch (status.warningLevel) {
    case 'dangerous_mixed':
      return 'DANGEROUS FULL LIVE';
    case 'armed_sell_only':
      return 'SELL ONLY ARMED';
    case 'blocked':
      return 'BLOCKED';
  }
  if (status.currentOperationMode == 'dry_run_simulation') return 'DRY RUN';
  if (status.currentOperationMode == 'manual_live_trading') {
    return 'MANUAL LIVE';
  }
  return 'SAFE';
}

List<_BadgeSpec> _readinessBadges(SchedulerStatus status) {
  final badges = <_BadgeSpec>[];
  if (_liveBuyArmed(status)) {
    badges.add(const _BadgeSpec('LIVE BUY ARMED', Colors.redAccent));
  }
  if (_liveSellArmed(status)) {
    badges.add(const _BadgeSpec('LIVE SELL ARMED', Colors.orangeAccent));
  }
  return badges;
}

Color _warningColor(String warningLevel) {
  switch (warningLevel) {
    case 'dangerous_mixed':
      return Colors.redAccent;
    case 'armed_sell_only':
      return Colors.orangeAccent;
    case 'blocked':
      return Colors.grey;
    default:
      return Colors.greenAccent;
  }
}

Color _onOffColor(bool enabled) {
  return enabled ? Colors.greenAccent : Colors.white70;
}

String _onOff(bool enabled) => enabled ? 'ON' : 'OFF';

String _yesNo(bool enabled) => enabled ? 'YES' : 'NO';

bool _liveBuyArmed(SchedulerStatus status) {
  return status.kr.liveBuyArmed ||
      status.riskSummary.liveBuyArmed ||
      status.liveBuyPossible;
}

bool _liveSellArmed(SchedulerStatus status) {
  return status.kr.liveSellArmed ||
      status.riskSummary.liveSellArmed ||
      status.liveSellPossible;
}

String _dailyRemaining(SchedulerStatus status) {
  final remaining = status.dailyLiveOrderRemaining ??
      status.riskSummary.dailyLiveOrderRemaining ??
      status.kr.riskSummary.dailyLiveOrderRemaining;
  return remaining == null ? 'Unknown' : remaining.toString();
}

String _formatScheduleTime(MarketSchedulerStatus status, String zoneLabel) {
  final display = _firstNonEmptyText([
    status.displayNextRun,
    _joinSchedule(status.nextSlotName, status.nextSlotTimeLocal),
  ]);
  if (display == null) return 'Not scheduled';
  return _withZone(display, zoneLabel);
}

String _formatCutoff(MarketSchedulerStatus status, String zoneLabel) {
  final display = _firstNonEmptyText([
    status.displayNoNewEntryAfter,
    status.noNewEntryAfter,
  ]);
  if (display == null) return 'Not configured';
  return _withZone(display, zoneLabel);
}

String? _joinSchedule(String? slotName, String? slotTime) {
  final time = slotTime?.trim();
  if (time == null || time.isEmpty) return null;
  final name = slotName?.trim();
  if (name == null || name.isEmpty) return time;
  return '$name $time';
}

String? _firstNonEmptyText(List<String?> values) {
  for (final value in values) {
    final text = value?.trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return null;
}

String _withZone(String value, String zoneLabel) {
  final trimmed = value.trim();
  final upper = trimmed.toUpperCase();
  final zone = zoneLabel.toUpperCase();
  if (upper.endsWith(' $zone') || upper.contains(' $zone ')) return trimmed;
  return '$trimmed $zoneLabel';
}

String _preLiveSummary({
  required PortfolioSummary summary,
  required int exitReviewCount,
  required int? preflightCandidateCount,
  required bool preparedSellTicket,
}) {
  if (preparedSellTicket) {
    return 'Manual sell ticket is prefilled. Continue in Trading: validate, check confirm_live manually, then submit if runtime gates allow.';
  }
  if (preflightCandidateCount != null && preflightCandidateCount > 0) {
    return 'Exit preflight found $preflightCandidateCount candidate(s). Prepare a manual sell ticket from the reviewed candidate.';
  }
  if (exitReviewCount > 0) {
    return '$exitReviewCount held position(s) need operator exit review before any manual ticket.';
  }
  if (summary.positionsUnavailable) {
    return 'KIS holdings are unavailable. Refresh positions before pre-live review.';
  }
  if (summary.positions.isEmpty) {
    return 'No held KIS positions loaded. Manual exit flow starts after holdings are visible.';
  }
  return 'KIS holdings are loaded. Run exit preflight before preparing any manual sell ticket.';
}

String _preLiveHoldingsLabel(PortfolioSummary summary) {
  if (summary.positionsUnavailable) return 'unavailable';
  return '${summary.positions.length} held';
}

String _preLiveValidationLabel({
  required Object? validation,
  required bool validationReady,
  required bool validationCurrent,
}) {
  if (validation == null) return 'not run';
  if (validationReady) return 'passed';
  if (!validationCurrent) return 'stale';
  return 'blocked';
}

Color _preLiveValidationColor({
  required Object? validation,
  required bool validationReady,
  required bool validationCurrent,
}) {
  if (validation == null) return Colors.white70;
  if (validationReady) return Colors.greenAccent;
  if (!validationCurrent) return Colors.amberAccent;
  return Colors.redAccent;
}
