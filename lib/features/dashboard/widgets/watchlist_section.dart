import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/candidate.dart';
import '../../../models/kis_auto_readiness.dart';
import '../../../models/kis_auto_simulator_result.dart';
import '../../../models/kis_exit_shadow_decision.dart';
import '../../../models/kis_shadow_exit_review.dart';
import '../../../models/kis_shadow_exit_review_queue.dart';
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
          _KisExitShadowDecisionCard(controller: controller),
          const SizedBox(height: 12),
          _KisShadowExitReviewCard(controller: controller),
          const SizedBox(height: 12),
          _KisShadowExitReviewQueueCard(controller: controller),
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
            child: Text('KIS Live Exit Manual Confirm',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: 'EXIT PREFLIGHT ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'MANUAL CONFIRM SELL', color: Colors.greenAccent),
          _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
          _SoftBadge(
              text: 'LIVE AUTO REMAINS DISABLED', color: Colors.amberAccent),
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
          _KisLiveExitPreflightResultPanel(
            result: result,
            controller: controller,
          ),
        ],
      ]),
    );
  }
}

class _KisExitShadowDecisionCard extends StatelessWidget {
  const _KisExitShadowDecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final result = controller.latestKisExitShadowDecision;
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
          const Icon(Icons.manage_search_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Exit Shadow Decision',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'SHADOW EXIT ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'DRY-RUN SELL SIMULATION', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO SELL DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: controller.kisExitShadowLoading
              ? null
              : () async {
                  final actionResult = await controller.runKisExitShadowOnce();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisExitShadowLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.rule_folder_outlined),
          label: Text(controller.kisExitShadowLoading
              ? 'Running shadow exit...'
              : 'Run Shadow Exit Once'),
        ),
        if (controller.kisExitShadowError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisExitShadowError!),
              color: Colors.redAccent),
        ],
        if (result != null) ...[
          const SizedBox(height: 10),
          _KisExitShadowDecisionPanel(
            result: result,
            controller: controller,
          ),
        ] else ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'No shadow decision run yet. Running this only records a dry-run decision.',
          ),
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewCard extends StatelessWidget {
  const _KisShadowExitReviewCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final review = controller.latestKisShadowExitReview;
    final summary = review?.summary;
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
          const Icon(Icons.analytics_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Shadow Exit Review',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'REVIEW ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'SHADOW DECISION QUALITY', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO SELL DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisShadowExitReviewLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisShadowExitReview();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisShadowExitReviewLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.kisShadowExitReviewLoading
              ? 'Refreshing review...'
              : 'Refresh Review only'),
        ),
        if (controller.kisShadowExitReviewError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisShadowExitReviewError!),
              color: Colors.redAccent),
        ],
        if (summary == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'Review not loaded yet. This card only reads historical shadow decisions.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisShadowExitReviewSummaryPanel(summary: summary),
          const SizedBox(height: 12),
          _StateLine(
            text: review!.safety.noSubmitInvariantOk
                ? 'No-submit invariant: OK'
                : 'No-submit invariant: historical warning found',
            color: review.safety.noSubmitInvariantOk
                ? Colors.greenAccent
                : Colors.redAccent,
          ),
          if (review.recentDecisions.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final decision in review.recentDecisions.take(5)) ...[
              _KisShadowExitReviewDecisionTile(decision: decision),
              const SizedBox(height: 8),
            ],
          ] else ...[
            const SizedBox(height: 12),
            const _StateLine(text: 'No shadow exit decisions in this window.'),
          ],
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewSummaryPanel extends StatelessWidget {
  const _KisShadowExitReviewSummaryPanel({required this.summary});

  final KisShadowExitReviewSummary summary;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(
          label: 'total shadow runs',
          value: summary.totalShadowRuns.toString()),
      _ResultPair(
          label: 'would sell count', value: summary.wouldSellCount.toString()),
      _ResultPair(label: 'hold count', value: summary.holdCount.toString()),
      _ResultPair(
          label: 'manual review count',
          value: summary.manualReviewCount.toString()),
      _ResultPair(
          label: 'would sell rate', value: _formatRate(summary.wouldSellRate)),
      _ResultPair(
          label: 'manual sell followed',
          value:
              '${summary.manualSellFollowedCount} / ${_formatRate(summary.manualSellFollowedRate)}'),
      _ResultPair(
          label: 'stop-loss count', value: summary.stopLossCount.toString()),
      _ResultPair(
          label: 'take-profit count',
          value: summary.takeProfitCount.toString()),
      _ResultPair(
          label: 'insufficient cost basis',
          value: summary.insufficientCostBasisCount.toString()),
      _ResultPair(
          label: 'no-submit invariant',
          value: summary.noSubmitInvariantOk ? 'OK' : 'WARNING'),
    ]);
  }
}

class _KisShadowExitReviewDecisionTile extends StatelessWidget {
  const _KisShadowExitReviewDecisionTile({required this.decision});

  final KisShadowExitReviewDecision decision;

  @override
  Widget build(BuildContext context) {
    final linkedStatus = decision.linkedManualOrderStatus;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(decision.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: _shadowDecisionLabel(decision.decision),
            color: decision.decision == 'would_sell'
                ? Colors.greenAccent
                : Colors.white70,
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'trigger', value: decision.trigger ?? 'n/a'),
          _ResultPair(
            label: 'unrealized P/L',
            value:
                '${_formatReviewKrwOrDash(decision.unrealizedPl)} / ${_formatReviewPlPercent(decision)}',
          ),
          _ResultPair(
            label: 'linked manual order',
            value: linkedStatus ?? 'n/a',
          ),
          if (decision.createdAt.isNotEmpty)
            _ResultPair(
              label: 'created_at',
              value: formatTimestampWithKst(decision.createdAt),
            ),
        ]),
        if (decision.reason.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: decision.reason),
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewQueueCard extends StatelessWidget {
  const _KisShadowExitReviewQueueCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final queue = controller.latestKisShadowExitReviewQueue;
    final summary = queue?.summary;
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
          const Icon(Icons.playlist_add_check_circle_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Shadow Exit Review Queue',
                style: Theme.of(context).textTheme.titleSmall),
          ),
        ]),
        const SizedBox(height: 8),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'OPERATOR REVIEW', color: Colors.lightBlueAccent),
          _SoftBadge(text: 'SHADOW EXIT ALERTS', color: Colors.greenAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(text: 'NO MANUAL SUBMIT', color: Colors.orangeAccent),
          _SoftBadge(
              text: 'LIVE AUTO SELL DISABLED', color: Colors.amberAccent),
          _SoftBadge(
              text: 'SCHEDULER REAL ORDERS DISABLED', color: Colors.redAccent),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: controller.kisShadowExitReviewQueueLoading
              ? null
              : () async {
                  final actionResult =
                      await controller.refreshKisShadowExitReviewQueue();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisShadowExitReviewQueueLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.refresh),
          label: Text(controller.kisShadowExitReviewQueueLoading
              ? 'Refreshing queue...'
              : 'Refresh Queue'),
        ),
        if (controller.kisShadowExitReviewQueueError != null) ...[
          const SizedBox(height: 10),
          _StateLine(
              text: _primaryLine(controller.kisShadowExitReviewQueueError!),
              color: Colors.redAccent),
        ],
        if (summary == null) ...[
          const SizedBox(height: 10),
          const _StateLine(
            text:
                'Queue not loaded yet. Review and dismiss actions only update local operator state.',
          ),
        ] else ...[
          const SizedBox(height: 10),
          _KisShadowExitReviewQueueSummaryPanel(summary: summary),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            _SoftBadge(
              text: 'read_only=${_boolText(queue!.safety.readOnly)}',
              color: Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text:
                  'real_order_submitted=${_boolText(queue.safety.realOrderSubmitted)}',
              color: Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text:
                  'broker_submit_called=${_boolText(queue.safety.brokerSubmitCalled)}',
              color: Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text:
                  'manual_submit_called=${_boolText(queue.safety.manualSubmitCalled)}',
              color: Colors.lightBlueAccent,
            ),
          ]),
          if (queue.items.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final item in queue.items.take(5)) ...[
              _KisShadowExitReviewQueueItemTile(
                item: item,
                controller: controller,
              ),
              const SizedBox(height: 8),
            ],
          ] else ...[
            const SizedBox(height: 12),
            const _StateLine(text: 'No open shadow exit review alerts.'),
          ],
        ],
      ]),
    );
  }
}

class _KisShadowExitReviewQueueSummaryPanel extends StatelessWidget {
  const _KisShadowExitReviewQueueSummaryPanel({required this.summary});

  final KisShadowExitReviewQueueSummary summary;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 14, runSpacing: 8, children: [
      _ResultPair(label: 'open count', value: summary.openCount.toString()),
      _ResultPair(
          label: 'reviewed count', value: summary.reviewedCount.toString()),
      _ResultPair(
          label: 'dismissed count', value: summary.dismissedCount.toString()),
      _ResultPair(
          label: 'would-sell open',
          value: summary.wouldSellOpenCount.toString()),
      _ResultPair(
          label: 'manual-review open',
          value: summary.manualReviewOpenCount.toString()),
      _ResultPair(
          label: 'repeated symbols',
          value: summary.repeatedSymbolCount.toString()),
      _ResultPair(
        label: 'latest open',
        value: summary.latestOpenAt == null
            ? 'n/a'
            : formatTimestampWithKst(summary.latestOpenAt),
      ),
    ]);
  }
}

class _KisShadowExitReviewQueueItemTile extends StatelessWidget {
  const _KisShadowExitReviewQueueItemTile({
    required this.item,
    required this.controller,
  });

  final KisShadowExitReviewQueueItem item;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final linkedStatus = item.linkedManualOrderStatus;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
            child: Text(item.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(
            text: _shadowDecisionLabel(item.decision),
            color: item.decision == 'would_sell'
                ? Colors.greenAccent
                : Colors.amberAccent,
          ),
          const SizedBox(width: 8),
          _SoftBadge(
            text: _queueStatusLabel(item.status),
            color: _queueStatusColor(item.status),
          ),
        ]),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'trigger', value: item.trigger),
          _ResultPair(
              label: 'occurrences', value: item.occurrenceCount.toString()),
          _ResultPair(
            label: 'latest P/L',
            value:
                '${_formatReviewKrwOrDash(item.latestUnrealizedPl)} / ${_formatQueuePlPercent(item)}',
          ),
          _ResultPair(
            label: 'linked manual order',
            value: linkedStatus ?? 'n/a',
          ),
          if (item.latestSeenAt != null)
            _ResultPair(
              label: 'latest_seen',
              value: formatTimestampWithKst(item.latestSeenAt),
            ),
        ]),
        if (item.reason.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: item.reason),
        ],
        if (item.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(item.riskFlags)}'),
        ],
        if (item.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(item.gatingNotes)}'),
        ],
        if (item.operatorNote?.isNotEmpty == true) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'operator_note: ${item.operatorNote!}'),
        ],
        if (item.isOpen) ...[
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 8, children: [
            OutlinedButton.icon(
              onPressed: controller.kisShadowExitReviewQueueLoading
                  ? null
                  : () async {
                      final result = await controller
                          .markKisShadowExitQueueItemReviewed(item.queueId);
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.check_circle_outline),
              label: const Text('Mark Reviewed'),
            ),
            TextButton.icon(
              onPressed: controller.kisShadowExitReviewQueueLoading
                  ? null
                  : () async {
                      final result = await controller
                          .dismissKisShadowExitQueueItem(item.queueId);
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
              icon: const Icon(Icons.close),
              label: const Text('Dismiss'),
            ),
          ]),
        ],
      ]),
    );
  }
}

class _KisExitShadowDecisionPanel extends StatelessWidget {
  const _KisExitShadowDecisionPanel({
    required this.result,
    required this.controller,
  });

  final KisExitShadowDecision result;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final candidate = result.candidate;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _StateLine(
        text: candidate == null
            ? 'HOLD. No shadow sell candidate was selected.'
            : '${_shadowDecisionLabel(result.decision)}. ${candidate.symbol} remains manual-confirm only.',
      ),
      const SizedBox(height: 10),
      Wrap(spacing: 8, runSpacing: 8, children: [
        _SoftBadge(
          text: 'decision=${_shadowDecisionLabel(result.decision)}',
          color: result.isWouldSell ? Colors.greenAccent : Colors.white70,
        ),
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
        _SoftBadge(
          text:
              'real_order_submit_allowed=${_boolText(result.realOrderSubmitAllowed)}',
          color: Colors.lightBlueAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'mode', value: result.mode),
        _ResultPair(label: 'action', value: result.action),
        _ResultPair(label: 'reason', value: result.reason),
        _ResultPair(
          label: 'auto_sell_enabled',
          value: _boolText(result.autoSellEnabled),
        ),
        _ResultPair(
          label: 'scheduler_real_order_enabled',
          value: _boolText(result.schedulerRealOrderEnabled),
        ),
        _ResultPair(
          label: 'manual_confirm_required',
          value: _boolText(result.manualConfirmRequired),
        ),
        if (result.createdAt != null)
          _ResultPair(
            label: 'created_at',
            value: formatTimestampWithKst(result.createdAt),
          ),
      ]),
      if (candidate != null) ...[
        const SizedBox(height: 12),
        _KisExitShadowCandidateCard(
          candidate: candidate,
          decision: result,
          controller: controller,
        ),
      ],
      const SizedBox(height: 10),
      _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
      if (result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'gating_notes: ${_joinList(result.gatingNotes)}'),
      ],
      if (result.candidatesEvaluated.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(
          text:
              'candidates_evaluated: ${result.candidatesEvaluated.length.toString()}',
        ),
      ],
    ]);
  }
}

class _KisExitShadowCandidateCard extends StatelessWidget {
  const _KisExitShadowCandidateCard({
    required this.candidate,
    required this.decision,
    required this.controller,
  });

  final KisExitShadowCandidate candidate;
  final KisExitShadowDecision decision;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.assignment_late_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(candidate.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(text: candidate.trigger, color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'WOULD SELL ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'MANUAL CONFIRM REQUIRED', color: Colors.greenAccent),
          _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'side', value: candidate.side),
          _ResultPair(
            label: 'quantity_available',
            value: _qtyText(candidate.quantityAvailable),
          ),
          _ResultPair(
            label: 'suggested_quantity',
            value: _qtyText(candidate.suggestedQuantity),
          ),
          _ResultPair(
            label: 'current_price',
            value: _formatKrwOrDash(candidate.currentPrice),
          ),
          _ResultPair(
            label: 'cost_basis',
            value: _formatKrwOrDash(candidate.costBasis),
          ),
          _ResultPair(
            label: 'current_value',
            value: _formatKrwOrDash(candidate.currentValue),
          ),
          _ResultPair(
            label: 'unrealized_pl',
            value: _formatKrwOrDash(candidate.unrealizedPl),
          ),
          _ResultPair(
            label: 'unrealized_pl_pct',
            value: _formatShadowPlPercent(candidate),
          ),
          _ResultPair(label: 'trigger', value: candidate.trigger),
          _ResultPair(label: 'trigger_source', value: candidate.triggerSource),
        ]),
        if (candidate.reason.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: candidate.reason),
        ],
        if (candidate.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(candidate.riskFlags)}'),
        ],
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(candidate.gatingNotes)}'),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text:
                'real_order_submit_allowed=${_boolText(candidate.realOrderSubmitAllowed)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'broker_submit_called=${_boolText(candidate.brokerSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'manual_submit_called=${_boolText(candidate.manualSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: candidate.suggestedQuantityInt == null
              ? null
              : () {
                  final actionResult =
                      controller.prepareKisManualSellFromShadowCandidate(
                    candidate,
                    decision: decision,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: const Icon(Icons.edit_note_outlined),
          label: const Text('Prepare Manual Sell Ticket'),
        ),
      ]),
    );
  }
}

class _KisLiveExitPreflightResultPanel extends StatelessWidget {
  const _KisLiveExitPreflightResultPanel({
    required this.result,
    required this.controller,
  });

  final KisLiveExitPreflightResult result;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final noHeldPosition = !result.hasHeldPosition ||
        result.blockedBy.contains('no_held_position');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (noHeldPosition) ...[
        const _StateLine(text: 'No held KIS position to evaluate.'),
        const SizedBox(height: 10),
      ] else if (result.candidates.isNotEmpty) ...[
        const _StateLine(
          text:
              'Exit candidate found. Manual confirmation is required before any live sell order.',
        ),
        const SizedBox(height: 10),
      ] else ...[
        const _StateLine(
          text: 'Hold / manual review only. No auto sell and no broker submit.',
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
        _SoftBadge(
          text:
              'real_order_submit_allowed=${_boolText(result.realOrderSubmitAllowed)}',
          color: Colors.lightBlueAccent,
        ),
        _SoftBadge(
          text:
              'manual_confirm_required=${_boolText(result.manualConfirmRequired)}',
          color: Colors.greenAccent,
        ),
        _SoftBadge(
          text: 'auto_sell_enabled=${_boolText(result.autoSellEnabled)}',
          color: Colors.amberAccent,
        ),
      ]),
      const SizedBox(height: 10),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _ResultPair(label: 'status', value: result.status),
        _ResultPair(label: 'mode', value: result.executionMode),
        _ResultPair(
          label: 'live_auto_enabled',
          value: _boolText(result.liveAutoEnabled),
        ),
        _ResultPair(
          label: 'candidate_count',
          value: result.candidateCount.toString(),
        ),
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
      if (result.candidates.isNotEmpty) ...[
        const SizedBox(height: 12),
        for (final candidate in result.candidates) ...[
          _KisLiveExitCandidateCard(
            candidate: candidate,
            preflight: result,
            controller: controller,
          ),
          const SizedBox(height: 10),
        ],
      ],
      const SizedBox(height: 10),
      _StateLine(text: 'blocked_by: ${_joinList(result.blockedBy)}'),
      const SizedBox(height: 8),
      _StateLine(text: 'risk_flags: ${_joinList(result.riskFlags)}'),
      if (result.gatingNotes.isNotEmpty) ...[
        const SizedBox(height: 8),
        _StateLine(text: 'gating_notes: ${_joinList(result.gatingNotes)}'),
      ],
    ]);
  }
}

class _KisLiveExitCandidateCard extends StatelessWidget {
  const _KisLiveExitCandidateCard({
    required this.candidate,
    required this.preflight,
    required this.controller,
  });

  final KisLiveExitCandidate candidate;
  final KisLiveExitPreflightResult preflight;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.assignment_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(candidate.symbol,
                style: Theme.of(context).textTheme.titleSmall),
          ),
          _SoftBadge(text: candidate.trigger, color: Colors.greenAccent),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(text: 'PREPARE ONLY', color: Colors.lightBlueAccent),
          _SoftBadge(
              text: 'MANUAL CONFIRM REQUIRED', color: Colors.greenAccent),
          _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          _SoftBadge(text: 'NO BROKER SUBMIT', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _ResultPair(label: 'side', value: candidate.side),
          _ResultPair(
            label: 'quantity_available',
            value: _qtyText(candidate.quantityAvailable),
          ),
          _ResultPair(
            label: 'suggested_quantity',
            value: _qtyText(candidate.suggestedQuantity),
          ),
          _ResultPair(
            label: 'current_price',
            value: _formatKrwOrDash(candidate.currentPrice),
          ),
          _ResultPair(
            label: 'cost_basis',
            value: _formatKrwOrDash(candidate.costBasis),
          ),
          _ResultPair(
            label: 'current_value',
            value: _formatKrwOrDash(candidate.currentValue),
          ),
          _ResultPair(
            label: 'unrealized_pl',
            value: _formatKrwOrDash(candidate.unrealizedPl),
          ),
          _ResultPair(
            label: 'unrealized_pl_pct',
            value: _formatSafePlPercent(candidate),
          ),
          _ResultPair(label: 'trigger_source', value: candidate.triggerSource),
          _ResultPair(label: 'severity', value: candidate.severity),
          _ResultPair(label: 'action_hint', value: candidate.actionHint),
          _ResultPair(
            label: 'submit_ready',
            value: _boolText(candidate.submitReady),
          ),
        ]),
        if (candidate.reason.isNotEmpty) ...[
          const SizedBox(height: 10),
          _StateLine(text: candidate.reason),
        ],
        if (candidate.riskFlags.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'risk_flags: ${_joinList(candidate.riskFlags)}'),
        ],
        if (candidate.gatingNotes.isNotEmpty) ...[
          const SizedBox(height: 8),
          _StateLine(text: 'gating_notes: ${_joinList(candidate.gatingNotes)}'),
        ],
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
            text:
                'real_order_submit_allowed=${_boolText(candidate.realOrderSubmitAllowed)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'broker_submit_called=${_boolText(candidate.brokerSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
          _SoftBadge(
            text:
                'manual_submit_called=${_boolText(candidate.manualSubmitCalled)}',
            color: Colors.lightBlueAccent,
          ),
        ]),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: candidate.suggestedQuantityInt == null
              ? null
              : () {
                  final actionResult =
                      controller.prepareKisManualSellFromExitCandidate(
                    candidate,
                    preflight: preflight,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(actionResult.message),
                    backgroundColor:
                        actionResult.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: const Icon(Icons.edit_note_outlined),
          label: const Text('Prepare Manual Sell Ticket'),
        ),
      ]),
    );
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

String _formatKrwOrDash(double? value) {
  if (value == null) return '--';
  return _formatKrw(value);
}

String _formatPercentFromDecimal(double? value) {
  if (value == null) return 'n/a';
  return _formatPercentValue(value * 100, signed: true);
}

String _formatSafePlPercent(KisLiveExitCandidate candidate) {
  if (!candidate.hasSafePlPct) return '--';
  return _formatPercentFromDecimal(candidate.unrealizedPlPct);
}

String _formatShadowPlPercent(KisExitShadowCandidate candidate) {
  if (!candidate.hasSafePlPct) return '--';
  return _formatPercentFromDecimal(candidate.unrealizedPlPct);
}

String _formatReviewPlPercent(KisShadowExitReviewDecision decision) {
  if (decision.unrealizedPlPct == null) return '--';
  return _formatPercentFromDecimal(decision.unrealizedPlPct);
}

String _formatQueuePlPercent(KisShadowExitReviewQueueItem item) {
  if (item.latestUnrealizedPlPct == null) return '--';
  return _formatPercentFromDecimal(item.latestUnrealizedPlPct);
}

String _formatReviewKrwOrDash(double? value) {
  if (value == null) return '--';
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
  return 'KRW $sign${buffer.toString()}';
}

String _shadowDecisionLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'would_sell') return 'WOULD SELL';
  if (normalized == 'manual_review') return 'MANUAL REVIEW';
  return 'HOLD';
}

String _queueStatusLabel(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'reviewed') return 'REVIEWED';
  if (normalized == 'dismissed') return 'DISMISSED';
  return 'OPEN';
}

Color _queueStatusColor(String value) {
  final normalized = value.trim().toLowerCase();
  if (normalized == 'reviewed') return Colors.greenAccent;
  if (normalized == 'dismissed') return Colors.white54;
  return Colors.lightBlueAccent;
}

String _formatPercentValue(double? value, {bool signed = false}) {
  if (value == null) return 'n/a';
  final sign = signed && value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(2)}%';
}

String _formatRate(double value) {
  return _formatPercentValue(value * 100);
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
