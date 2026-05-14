import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/candidate.dart';
import '../../../models/kis_auto_readiness.dart';
import '../../../models/kis_auto_simulator_result.dart';
import '../../../models/kis_live_exit_preflight.dart';
import '../../../models/kis_scheduler_simulation.dart';
import '../../../models/market_watchlist.dart';
import '../../dashboard/dashboard_controller.dart';

class WatchlistSection extends StatelessWidget {
  const WatchlistSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final isKr = controller.selectedProvider == SelectedProvider.kis;
    final watchlist = isKr ? controller.krWatchlist : controller.usWatchlist;
    final title = isKr ? 'KR Watchlist / KIS' : 'US Watchlist / Alpaca';

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.format_list_bulleted, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Watchlist',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          _CountPill(text: '${watchlist.count} symbols'),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          Text(title,
              style: const TextStyle(
                  color: Colors.white70, fontWeight: FontWeight.w800)),
          if (isKr) ...[
            const _SoftBadge(
                text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
            const _SoftBadge(
                text: 'TRADING DISABLED', color: Colors.amberAccent),
            const _SoftBadge(text: 'NO AUTO ORDER', color: Colors.orangeAccent),
          ],
        ]),
        const SizedBox(height: 12),
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(value: 1, label: Text('Gate 1')),
            ButtonSegment(value: 2, label: Text('Gate 2')),
            ButtonSegment(value: 3, label: Text('Gate 3')),
            ButtonSegment(value: 4, label: Text('Gate 4')),
          ],
          selected: {controller.selectedGateLevel},
          onSelectionChanged: (selection) =>
              controller.setSelectedGateLevel(selection.first),
        ),
        const SizedBox(height: 12),
        if (controller.watchlistLoading)
          const LinearProgressIndicator(minHeight: 2)
        else if (watchlist.symbols.isEmpty)
          _StateLine(
              text: isKr
                  ? 'No KR watchlist symbols available'
                  : 'No US watchlist symbols available')
        else
          _WatchlistSymbols(watchlist: watchlist, isKr: isKr),
        if (controller.watchlistError != null) ...[
          const SizedBox(height: 10),
          _StateLine(text: controller.watchlistError!, color: Colors.redAccent),
        ],
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.runOnceLoading
              ? null
              : () async {
                  final result = await controller.runOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.runOnceLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : Icon(isKr ? Icons.preview_outlined : Icons.play_arrow),
          label: Text(controller.runOnceLoading
              ? (isKr
                  ? 'Running KIS preview...'
                  : 'Running Alpaca watchlist...')
              : (isKr ? 'Run KIS Preview' : 'Run Alpaca Watchlist')),
        ),
        if (isKr &&
            controller.hasLatestRunResult &&
            controller.runResult.finalRankedCandidates.isNotEmpty &&
            _isKisPreviewCandidate(
                controller.runResult.finalRankedCandidates.first)) ...[
          const SizedBox(height: 12),
          _KisPreviewAdvisoryPanel(
            candidate: controller.runResult.finalRankedCandidates.first,
          ),
        ],
        if (isKr) ...[
          const SizedBox(height: 12),
          _KisLiveAutoReadinessCard(controller: controller),
          const SizedBox(height: 12),
          _KisAutoSimulatorPanel(controller: controller),
          const SizedBox(height: 12),
          _KisSchedulerSimulationPanel(controller: controller),
          const SizedBox(height: 12),
          _KisLiveExitPreflightCard(controller: controller),
        ],
      ]),
    );
  }
}

class _KisLiveAutoReadinessCard extends StatelessWidget {
  const _KisLiveAutoReadinessCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result =
        controller.kisAutoReadinessResult ?? KisAutoReadiness.safeDefault();
    final liveAutoLabel =
        result.liveAutoEnabled ? 'enabled flag / submit blocked' : 'disabled';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.security_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Live Auto Readiness',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          IconButton(
            tooltip: 'Refresh KIS auto readiness',
            onPressed: controller.kisAutoReadinessLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisAutoReadiness();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisAutoReadinessLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'READINESS ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'LIVE AUTO DISABLED', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'MANUAL CONFIRM REQUIRED', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(
              label: 'auto_order_ready',
              value: _boolText(result.autoOrderReady)),
          _ResultPair(label: 'live auto order', value: liveAutoLabel),
          _ResultPair(
              label: 'real_order_submit_allowed',
              value: _boolText(result.realOrderSubmitAllowed)),
          _ResultPair(
              label: 'future readiness',
              value: _boolText(result.futureAutoOrderReady)),
          _ResultPair(label: 'preflight', value: _boolText(result.preflight)),
          _ResultPair(
              label: 'reason',
              value: result.reason.isEmpty ? 'n/a' : result.reason),
        ]),
        if (!controller.kisAutoReadinessLoaded &&
            controller.kisAutoReadinessResult == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text: 'Readiness not loaded yet. Safe default: live auto blocked.',
          ),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text: 'auto_order_ready=${_boolText(result.autoOrderReady)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'real_order_submit_allowed=${_boolText(result.realOrderSubmitAllowed)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "real_order_submitted=${_boolText(result.safetyFlag('real_order_submitted'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "broker_submit_called=${_boolText(result.safetyFlag('broker_submit_called'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "manual_submit_called=${_boolText(result.safetyFlag('manual_submit_called'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "scheduler_real_order_enabled=${_boolText(result.safetyFlag('scheduler_real_order_enabled'))}",
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                "requires_manual_confirm=${_boolText(result.safetyFlag('requires_manual_confirm'))}",
            color: Colors.greenAccent,
          ),
        ]),
        const SizedBox(height: 10),
        _KisAutoReadinessChecks(result: result),
        if (result.blockedBy.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
        ],
        if (controller.kisAutoReadinessError != null) ...[
          const SizedBox(height: 10),
          _RetryLine(
            text: _primaryLine(controller.kisAutoReadinessError!),
            onRetry: controller.kisAutoReadinessLoading
                ? null
                : controller.refreshKisAutoReadiness,
          ),
        ],
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          OutlinedButton.icon(
            onPressed: controller.kisAutoReadinessLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisAutoReadiness();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: const Icon(Icons.refresh),
            label: Text(controller.kisAutoReadinessLoading
                ? 'Refreshing...'
                : 'Refresh'),
          ),
          FilledButton.icon(
            onPressed: controller.kisAutoPreflightLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.runKisAutoPreflightOnce();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisAutoPreflightLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.fact_check_outlined),
            label: Text(controller.kisAutoPreflightLoading
                ? 'Running preflight...'
                : 'Run Preflight Once'),
          ),
        ]),
      ]),
    );
  }
}

class _KisAutoReadinessChecks extends StatelessWidget {
  const _KisAutoReadinessChecks({required this.result});

  final KisAutoReadiness result;

  @override
  Widget build(BuildContext context) {
    const keys = [
      'dry_run',
      'kill_switch',
      'kis_enabled',
      'kis_real_order_enabled',
      'kis_scheduler_enabled',
      'kis_scheduler_allow_real_orders',
      'market_open',
      'entry_allowed_now',
      'daily_loss_ok',
      'trade_limit_ok',
      'gpt_context_available',
      'risk_engine_ok',
      'live_auto_buy_enabled',
      'live_auto_sell_enabled',
    ];
    return Wrap(spacing: 14, runSpacing: 8, children: [
      for (final key in keys)
        _ResultPair(label: key, value: _boolText(result.check(key))),
    ]);
  }
}

class _KisLiveExitPreflightCard extends StatelessWidget {
  const _KisLiveExitPreflightCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.kisLiveExitPreflightResult;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.logout_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Live Exit Preflight',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'EXIT ONLY', color: Colors.greenAccent),
          _SoftBadge(text: 'PREFLIGHT ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO STILL DISABLED', color: Colors.amberAccent),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisLiveExitPreflightLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisLiveExitPreflight();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisLiveExitPreflightLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.fact_check_outlined),
          label: Text(controller.kisLiveExitPreflightLoading
              ? 'Running exit preflight...'
              : 'Run Exit Preflight'),
        ),
        if (controller.kisLiveExitPreflightError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisLiveExitPreflightError!),
              color: Colors.redAccent),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisLiveExitPreflightResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisLiveExitPreflightResultPanel extends StatelessWidget {
  const _KisLiveExitPreflightResultPanel({required this.result});

  final KisLiveExitPreflightResult result;

  @override
  Widget build(BuildContext context) {
    final noHeldPosition = !result.hasHeldPosition ||
        result.blockedBy.contains('no_held_position');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (noHeldPosition) ...[
        const _StateLine(text: 'No held KIS position to evaluate.'),
        const SizedBox(height: 10),
      ] else if (result.isSellCandidate) ...[
        const _StateLine(
          text: 'Exit candidate found, but live automation is still disabled.',
        ),
        const SizedBox(height: 10),
      ],
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'real_order_submitted=${_boolText(result.realOrderSubmitted)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'broker_submit_called=${_boolText(result.brokerSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'manual_submit_called=${_boolText(result.manualSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'symbol', value: result.symbol ?? 'n/a'),
        _ResultPair(label: 'qty', value: _qtyText(result.qty)),
        _ResultPair(
          label: 'estimated_notional',
          value: _formatKrw(result.estimatedNotional),
        ),
        if (result.costBasis != null)
          _ResultPair(
            label: 'cost_basis',
            value: _formatKrw(result.costBasis),
          ),
        if (result.currentValue != null)
          _ResultPair(
            label: 'current_value',
            value: _formatKrw(result.currentValue),
          ),
        if (result.unrealizedPl != null)
          _ResultPair(
            label: 'unrealized_pl',
            value: _formatKrw(result.unrealizedPl),
          ),
        if (result.unrealizedPlPct != null)
          _ResultPair(
            label: 'unrealized_pl_pct',
            value: _formatPercentFromDecimal(result.unrealizedPlPct),
          ),
        if (result.takeProfitThresholdPct != null)
          _ResultPair(
            label: 'take_profit_threshold',
            value: _formatPercentValue(result.takeProfitThresholdPct),
          ),
        if (result.stopLossThresholdPct != null)
          _ResultPair(
            label: 'stop_loss_threshold',
            value: _formatPercentValue(result.stopLossThresholdPct),
          ),
        if (result.exitTriggerSource != null)
          _ResultPair(
            label: 'exit_trigger_source',
            value: result.exitTriggerSource!,
          ),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(
          label: 'would_submit_if_enabled',
          value: _boolText(result.wouldSubmitIfEnabled),
        ),
      ]),
      const SizedBox(height: 10),
      _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
      const SizedBox(height: 8),
      _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
    ]);
  }
}

class _KisSchedulerSimulationPanel extends StatelessWidget {
  const _KisSchedulerSimulationPanel({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.kisSchedulerStatus;
    final result = controller.kisSchedulerRunResult;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.schedule_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Scheduler Simulation',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          IconButton(
            tooltip: 'Refresh KIS scheduler status',
            onPressed: controller.kisSchedulerStatusLoading
                ? null
                : () async {
                    final actionResult =
                        await controller.refreshKisSchedulerStatus();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(actionResult.message),
                      backgroundColor: actionResult.success
                          ? Colors.green
                          : Colors.redAccent,
                    ));
                  },
            icon: controller.kisSchedulerStatusLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'DISABLED BY DEFAULT', color: Colors.amberAccent),
          const _SoftBadge(text: 'DRY-RUN ONLY', color: Colors.greenAccent),
          const _SoftBadge(
              text: 'REAL ORDER SCHEDULER DISABLED',
              color: Colors.orangeAccent),
          _SoftBadge(
              text:
                  'real_orders_allowed=${_boolText(status.realOrdersAllowed)}',
              color: Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 10),
        _KisSchedulerStatusGrid(status: status),
        if (!controller.kisSchedulerStatusLoaded &&
            controller.kisSchedulerStatusError == null) ...[
          const SizedBox(height: 10),
          const _StateLine(text: 'Status not loaded yet.'),
        ],
        if (controller.kisSchedulerStatusError != null) ...[
          const SizedBox(height: 10),
          _RetryLine(
            text: _primaryLine(controller.kisSchedulerStatusError!),
            onRetry: controller.kisSchedulerStatusLoading
                ? null
                : controller.refreshKisSchedulerStatus,
          ),
        ],
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisSchedulerRunLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.runKisSchedulerDryRunOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisSchedulerRunLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_circle_outline),
          label: Text(controller.kisSchedulerRunLoading
              ? 'Running scheduler dry-run...'
              : 'Run KIS Scheduler Dry-Run Once'),
        ),
        if (controller.kisSchedulerRunError != null) ...[
          const SizedBox(height: 10),
          _RetryLine(
            text: _primaryLine(controller.kisSchedulerRunError!),
            onRetry: controller.kisSchedulerRunLoading
                ? null
                : controller.runKisSchedulerDryRunOnce,
          ),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisSchedulerResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisSchedulerStatusGrid extends StatelessWidget {
  const _KisSchedulerStatusGrid({required this.status});

  final KisSchedulerSimulationStatus status;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(label: 'enabled', value: _boolText(status.enabled)),
      _ResultPair(label: 'dry_run', value: _boolText(status.dryRun)),
      _ResultPair(
          label: 'allow_real_orders', value: _boolText(status.allowRealOrders)),
      _ResultPair(
          label: 'real_orders_allowed',
          value: _boolText(status.realOrdersAllowed)),
      _ResultPair(
        label: 'real_order_scheduler_enabled',
        value: _boolText(status.realOrderSchedulerEnabled),
      ),
      _ResultPair(
        label: 'runtime_scheduler_enabled',
        value: _nullableBoolText(status.runtimeSchedulerEnabled),
      ),
      _ResultPair(
        label: 'runtime_dry_run',
        value: _nullableBoolText(status.runtimeDryRun),
      ),
      _ResultPair(
        label: 'kill_switch',
        value: _nullableBoolText(status.killSwitch),
      ),
    ]);
  }
}

class _KisSchedulerResultPanel extends StatelessWidget {
  const _KisSchedulerResultPanel({required this.result});

  final KisSchedulerRunResult result;

  @override
  Widget build(BuildContext context) {
    final reason = result.reason.isNotEmpty
        ? result.reason
        : result.triggerBlockReason ?? '';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'real_order_submitted=${_boolText(result.realOrderSubmitted)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'broker_submit_called=${_boolText(result.brokerSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text: 'manual_submit_called=${_boolText(result.manualSubmitCalled)}',
          color: Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'result', value: result.result),
        _ResultPair(
            label: 'triggered symbol', value: result.triggeredSymbol ?? 'n/a'),
        _ResultPair(
            label: 'signal_id', value: result.signalId?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'order_id', value: result.orderId?.toString() ?? 'n/a'),
        if (result.createdAt?.isNotEmpty == true)
          _ResultPair(
              label: 'created_at',
              value: formatTimestampWithKst(result.createdAt)),
        _ResultPair(label: 'reason', value: reason.isEmpty ? 'n/a' : reason),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'dry_run', value: _boolText(result.dryRun)),
        _ResultPair(label: 'simulated', value: _boolText(result.simulated)),
        _ResultPair(
            label: 'scheduler_dry_run',
            value: _boolText(result.schedulerDryRun)),
        _ResultPair(
          label: 'scheduler_allow_real_orders',
          value: _boolText(result.schedulerAllowRealOrders),
        ),
      ]),
      if (result.aiBuyScore != null ||
          result.aiSellScore != null ||
          result.confidence != null ||
          result.riskFlags.isNotEmpty ||
          result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 10),
        const _StateLine(
            text: 'GPT Advisory Context - Preview Only - No Broker Submit'),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'ai_buy_score', value: _score(result.aiBuyScore)),
          _ResultPair(
              label: 'ai_sell_score', value: _score(result.aiSellScore)),
          _ResultPair(label: 'confidence', value: _score(result.confidence)),
          _ResultPair(
              label: 'final_entry_score',
              value: _score(result.finalEntryScore)),
          _ResultPair(
              label: 'event_risk', value: _eventRiskLabel(result.eventRisk)),
          _ResultPair(
              label: 'indicator_status',
              value: result.indicatorStatus ?? 'n/a'),
        ]),
        if (result.gptReason?.isNotEmpty == true) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gpt_reason: ${result.gptReason!}'),
        ],
        const SizedBox(height: 8),
        if (result.riskFlags.isNotEmpty)
          _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
        if (result.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(result.gatingNotes)}'),
        ],
      ],
    ]);
  }
}

class _KisPreviewAdvisoryPanel extends StatelessWidget {
  const _KisPreviewAdvisoryPanel({required this.candidate});

  final Candidate candidate;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.psychology_alt_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS GPT Advisory Context',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'symbol', value: candidate.symbol),
          _ResultPair(
              label: 'ai_buy_score', value: _score(candidate.aiBuyScore)),
          _ResultPair(
              label: 'ai_sell_score', value: _score(candidate.aiSellScore)),
          _ResultPair(label: 'confidence', value: _score(candidate.confidence)),
          _ResultPair(
              label: 'event_risk', value: candidate.eventRiskLevel ?? 'n/a'),
          _ResultPair(
              label: 'indicator_status',
              value: candidate.indicatorStatus.isEmpty
                  ? 'n/a'
                  : candidate.indicatorStatus),
          _ResultPair(
              label: 'final_buy_score', value: _score(candidate.finalBuyScore)),
          _ResultPair(
              label: 'final_sell_score',
              value: _score(candidate.finalSellScore)),
        ]),
        if (candidate.gptReason.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gpt_reason: ${candidate.gptReason}'),
        ],
        if (candidate.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(candidate.riskFlags)}'),
        ],
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(candidate.gatingNotes)}'),
        ],
      ]),
    );
  }
}

class _RetryLine extends StatelessWidget {
  const _RetryLine({required this.text, required this.onRetry});

  final String text;
  final Future<ActionResult> Function()? onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.redAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.redAccent.withValues(alpha: 0.20)),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(text, style: const TextStyle(color: Colors.redAccent)),
          TextButton.icon(
            onPressed: onRetry == null
                ? null
                : () async {
                    final result = await onRetry!();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: const Icon(Icons.refresh, size: 16),
            label: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

class _KisAutoSimulatorPanel extends StatelessWidget {
  const _KisAutoSimulatorPanel({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.kisAutoSimulatorResult;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.science_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Auto Simulator',
                style: Theme.of(context).textTheme.titleSmall),
          ),
          const _SoftBadge(text: 'Dry-run only', color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        FilledButton.icon(
          onPressed: controller.kisAutoSimulatorLoading
              ? null
              : () async {
                  final actionResult = await controller.runKisDryRunAuto();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisAutoSimulatorLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.play_circle_outline),
          label: Text(controller.kisAutoSimulatorLoading
              ? 'Running KIS dry-run...'
              : 'Run KIS Dry-Run Auto'),
        ),
        if (controller.kisAutoSimulatorError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisAutoSimulatorError!),
              color: Colors.redAccent),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisAutoSimulatorResultPanel(result: result),
        ],
      ]),
    );
  }
}

class _KisAutoSimulatorResultPanel extends StatelessWidget {
  const _KisAutoSimulatorResultPanel({required this.result});

  final KisAutoSimulatorResult result;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        const _SoftBadge(
            text: 'real_order_submitted=false', color: Colors.lightBlueAccent),
        _SoftBadge(
          text: result.result.isEmpty ? 'skipped' : result.result,
          color:
              result.orderId == null ? Colors.amberAccent : Colors.greenAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'Action', value: result.action.toUpperCase()),
        _ResultPair(label: 'Result', value: result.result),
        _ResultPair(label: 'Symbol', value: result.triggeredSymbol ?? 'n/a'),
        _ResultPair(
            label: 'Signal', value: result.signalId?.toString() ?? 'n/a'),
        _ResultPair(
            label: 'Sim Order', value: result.orderId?.toString() ?? 'n/a'),
        _ResultPair(label: 'Quant', value: _score(result.quantBuyScore)),
        _ResultPair(label: 'GPT', value: _gptScore(result)),
        _ResultPair(label: 'Final', value: _score(result.finalEntryScore)),
      ]),
      if (result.reason.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: result.reason),
      ],
    ]);
  }
}

class _ResultPair extends StatelessWidget {
  const _ResultPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(label.toUpperCase(),
          style: const TextStyle(
              color: Colors.white38,
              fontSize: 10,
              fontWeight: FontWeight.w700)),
      const SizedBox(height: 3),
      Text(value,
          style: const TextStyle(
              color: Colors.white70, fontWeight: FontWeight.w700)),
    ]);
  }
}

class _WatchlistSymbols extends StatelessWidget {
  const _WatchlistSymbols({required this.watchlist, required this.isKr});

  final MarketWatchlist watchlist;
  final bool isKr;

  @override
  Widget build(BuildContext context) {
    final visible = watchlist.symbols.take(isKr ? 8 : 16).toList();
    return Wrap(spacing: 8, runSpacing: 8, children: [
      for (final item in visible) _SymbolChip(item: item, isKr: isKr),
    ]);
  }
}

class _SymbolChip extends StatelessWidget {
  const _SymbolChip({required this.item, required this.isKr});

  final WatchlistSymbol item;
  final bool isKr;

  @override
  Widget build(BuildContext context) {
    final label = isKr && item.name.isNotEmpty
        ? '${item.symbol} - ${item.name} - ${item.market}'
        : item.symbol;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Text(label,
          style: const TextStyle(
              color: Colors.white70, fontWeight: FontWeight.w700)),
    );
  }
}

class _StateLine extends StatelessWidget {
  const _StateLine({required this.text, this.color = Colors.white60});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Text(text, style: TextStyle(color: color)),
    );
  }
}

class _SoftBadge extends StatelessWidget {
  const _SoftBadge({required this.text, required this.color});

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
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}

class _CountPill extends StatelessWidget {
  const _CountPill({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Text(text,
          style: const TextStyle(
              color: Colors.white70,
              fontSize: 11,
              fontWeight: FontWeight.w700)),
    );
  }
}

String _score(double? value) {
  if (value == null) return 'n/a';
  return value.toStringAsFixed(value.truncateToDouble() == value ? 0 : 1);
}

String _boolText(bool value) => value ? 'true' : 'false';

String _nullableBoolText(bool? value) {
  if (value == null) return 'n/a';
  return _boolText(value);
}

String _qtyText(double? value) {
  if (value == null) return 'n/a';
  return value.truncateToDouble() == value
      ? value.toStringAsFixed(0)
      : value.toStringAsFixed(2);
}

String _formatKrw(double? value) {
  if (value == null) return 'n/a';
  final sign = value < 0 ? '-' : '';
  final rounded = value.abs().round().toString();
  final buffer = StringBuffer();
  for (var index = 0; index < rounded.length; index += 1) {
    final remaining = rounded.length - index;
    buffer.write(rounded[index]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return '${sign}₩${buffer.toString()}';
}

String _formatPercentFromDecimal(double? value) {
  if (value == null) return 'n/a';
  return _formatPercentValue(value * 100, signed: true);
}

String _formatPercentValue(double? value, {bool signed = false}) {
  if (value == null) return 'n/a';
  final sign = signed && value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(2)}%';
}

String _joinList(List<String> values) {
  final items = values.where((item) => item.trim().isNotEmpty).toList();
  return items.isEmpty ? 'n/a' : items.join(', ');
}

bool _isKisPreviewCandidate(Candidate candidate) {
  final market = candidate.market.trim().toUpperCase();
  return candidate.currency.trim().toUpperCase() == 'KRW' ||
      market == 'KR' ||
      market == 'KOSPI' ||
      market == 'KOSDAQ' ||
      candidate.riskFlags.contains('kr_trading_disabled') ||
      candidate.riskFlags.contains('preview_only');
}

String _eventRiskLabel(Map<String, dynamic>? value) {
  if (value == null || value.isEmpty) return 'n/a';
  final riskLevel = value['risk_level']?.toString();
  final eventType = value['event_type']?.toString();
  if (riskLevel == null || riskLevel.isEmpty) return 'n/a';
  if (eventType == null || eventType.isEmpty || eventType == 'null') {
    return riskLevel;
  }
  return '$riskLevel / $eventType';
}

String _gptScore(KisAutoSimulatorResult result) {
  if (result.aiBuyScore != null) return _score(result.aiBuyScore);
  if (result.confidence != null) {
    return 'conf ${result.confidence!.toStringAsFixed(2)}';
  }
  return 'n/a';
}

String _primaryLine(String value) {
  final lines = value
      .split(RegExp(r'[\r\n]+'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty);
  return lines.isEmpty ? value.trim() : lines.first;
}
