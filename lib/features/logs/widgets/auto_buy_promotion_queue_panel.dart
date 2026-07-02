import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/strategy_auto_buy_promotion.dart';
import '../../../models/strategy_live_auto_buy.dart';
import '../../dashboard/dashboard_controller.dart';

class AutoBuyPromotionQueuePanel extends StatelessWidget {
  const AutoBuyPromotionQueuePanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final loading = controller.strategyAutoBuyPromotionsLoading ||
            controller.strategyLiveAutoBuyPreflightLoading ||
            controller.strategyLiveAutoBuyLoading;
        final items = controller.strategyAutoBuyPromotions;
        return Container(
          key: const ValueKey('auto-buy-promotion-queue-panel'),
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.20),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
          ),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.playlist_add_check_circle_outlined,
                        color: Colors.amberAccent, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            strings.autoBuyPromotionQueue,
                            style: const TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            strings.promotionTraceCount(items.length),
                            style: const TextStyle(color: Colors.white70),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      key: const ValueKey('refresh-promotions-button'),
                      tooltip: strings.refreshPromotions,
                      onPressed: loading
                          ? null
                          : () => _refresh(context, showSnack: true),
                      icon: const Icon(Icons.refresh),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                _BadgeWrap(badges: strings.promotionSafetyBadges),
                if (controller.strategyAutoBuyPromotionsError != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    controller.strategyAutoBuyPromotionsError!,
                    style: const TextStyle(color: Colors.orangeAccent),
                  ),
                ],
                if (loading && items.isEmpty) ...[
                  const SizedBox(height: 12),
                  const LinearProgressIndicator(),
                ],
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    OutlinedButton.icon(
                      key: const ValueKey('refresh-promotions-action'),
                      onPressed: loading
                          ? null
                          : () => _refresh(context, showSnack: true),
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(strings.refreshPromotions),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (items.isEmpty)
                  Text(
                    strings.noPromotionTraces,
                    style: const TextStyle(color: Colors.white70),
                  )
                else
                  Column(
                    children: [
                      for (final item in items)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _PromotionTile(
                            promotion: item,
                            strings: strings,
                            loading: loading,
                            liveReady: controller
                                    .strategyAutoBuyOperationsStatus
                                    ?.liveReadiness
                                    .ready ==
                                true,
                            preflight: controller
                                .strategyLiveAutoBuyPreflightForPromotion(
                              item.id,
                            ),
                            onMarkReviewed: () => _markReviewed(context, item),
                            onDismiss: () => _dismiss(context, item),
                            onPreflight: () => _preflight(context, item),
                            onConvert: () => _confirmLiveRun(context, item),
                          ),
                        ),
                    ],
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _refresh(
    BuildContext context, {
    required bool showSnack,
  }) async {
    final result = await controller.refreshStrategyAutoBuyPromotions();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _markReviewed(
    BuildContext context,
    StrategyAutoBuyPromotion promotion,
  ) async {
    final result = await controller.markStrategyAutoBuyPromotionReviewed(
      promotion,
    );
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  Future<void> _dismiss(
    BuildContext context,
    StrategyAutoBuyPromotion promotion,
  ) async {
    final result = await controller.dismissStrategyAutoBuyPromotion(
      promotion,
    );
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  Future<void> _preflight(
    BuildContext context,
    StrategyAutoBuyPromotion promotion,
  ) async {
    final result = await controller.preflightGuardedLiveAutoBuyForPromotion(
      promotion,
    );
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  Future<void> _confirmLiveRun(
    BuildContext context,
    StrategyAutoBuyPromotion promotion,
  ) async {
    final strings = controller.strings;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        key: const ValueKey('promotion-live-confirm-dialog'),
        title: Text(strings.liveConversionRequiresFinalConfirmation),
        content: Text(
          strings.convertPromotionConfirm(promotion.symbol ?? '-'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(strings.cancel),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(true),
            icon: const Icon(Icons.verified_user_outlined),
            label: Text(strings.convertViaGuardedLiveBuy),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final result = await controller.runGuardedLiveAutoBuyForPromotion(
      promotion,
    );
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _PromotionTile extends StatelessWidget {
  const _PromotionTile({
    required this.promotion,
    required this.strings,
    required this.loading,
    required this.liveReady,
    required this.preflight,
    required this.onMarkReviewed,
    required this.onDismiss,
    required this.onPreflight,
    required this.onConvert,
  });

  final StrategyAutoBuyPromotion promotion;
  final AppStrings strings;
  final bool loading;
  final bool liveReady;
  final StrategyLiveAutoBuyPreflightResult? preflight;
  final VoidCallback onMarkReviewed;
  final VoidCallback onDismiss;
  final VoidCallback onPreflight;
  final VoidCallback onConvert;

  @override
  Widget build(BuildContext context) {
    final score = promotion.finalScore ?? promotion.buyScore;
    final preflightBlocksConvert = preflight != null && !preflight!.isAllowed;
    final canConvert =
        promotion.canRunGuardedLive && liveReady && !preflightBlocksConvert;
    final converted = promotion.isConverted;
    final reviewLabel = strings.statusLabel(
      promotion.reviewStatus ?? promotion.status,
    );
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.055),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  '${promotion.symbol ?? '-'} ${promotion.symbolName ?? ''}',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                converted
                    ? strings.converted
                    : strings.statusLabel(promotion.status),
                style: const TextStyle(
                  color: Colors.amberAccent,
                  fontSize: 11,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 6,
            children: [
              _Metric(label: strings.score, value: _number(score)),
              _Metric(
                label: strings.confidence,
                value: _number(promotion.confidence),
              ),
              _Metric(
                label: strings.proposed,
                value: _money(
                  promotion.proposedNotionalKrw ??
                      promotion.recommendedNotionalKrw ??
                      promotion.simulatedNotionalKrw,
                ),
              ),
              _Metric(
                label: strings.maxNotional,
                value: _money(promotion.maxNotionalKrw),
              ),
              _Metric(
                label: strings.qty,
                value: _number(promotion.simulatedQuantity),
              ),
              _Metric(
                label: strings.price,
                value: _money(promotion.simulatedPrice),
              ),
              _Metric(
                label: strings.expires,
                value: promotion.expiresAt == null
                    ? '-'
                    : formatTimestampWithKst(
                        promotion.expiresAt!.toIso8601String(),
                      ),
              ),
              _Metric(
                label: strings.age,
                value: promotion.promotionAgeMinutes == null
                    ? '-'
                    : '${_number(promotion.promotionAgeMinutes)} min',
              ),
              if (promotion.liveAttemptId != null)
                _Metric(
                  label: strings.liveAttempt,
                  value: promotion.liveAttemptId.toString(),
                ),
              if (promotion.liveOrderId != null)
                _Metric(
                  label: strings.order,
                  value: promotion.liveOrderId.toString(),
                ),
              if (promotion.lastSyncStatus != null)
                _Metric(
                  label: strings.sync,
                  value: strings.statusLabel(promotion.lastSyncStatus!),
                ),
            ],
          ),
          const SizedBox(height: 8),
          _DetailRow(
            label: strings.review,
            value:
                promotion.reviewRequired ? strings.reviewRequired : reviewLabel,
          ),
          _DetailRow(
            label: strings.action,
            value: promotion.dryRunAction == null
                ? '-'
                : strings.statusLabel(promotion.dryRunAction!),
          ),
          _DetailRow(
            label: strings.reason,
            value: promotion.promotionReason ?? promotion.blockReason ?? '-',
          ),
          if (promotion.reviewSummary != null)
            _DetailRow(
              label: strings.summary,
              value: promotion.reviewSummary!,
            ),
          if (promotion.primaryRiskNote != null)
            _DetailRow(
              label: strings.riskNote,
              value: promotion.primaryRiskNote!,
            ),
          _DetailRow(
            label: strings.dryRunIds,
            value:
                'signal ${promotion.sourceDryRunSignalId ?? '-'} / run ${promotion.sourceDryRunTradeRunId ?? '-'} / order ${promotion.sourceDryRunOrderId ?? '-'}',
          ),
          if (promotion.riskFlags.isNotEmpty)
            _DetailRow(
                label: strings.riskFlags,
                value: promotion.riskFlags.join(', ')),
          if (promotion.gatingNotes.isNotEmpty)
            _DetailRow(
                label: strings.gates, value: promotion.gatingNotes.join(' | ')),
          if (promotion.isExpired)
            _DetailRow(
              label: strings.warning,
              value: strings.promotionExpiredWarning,
            ),
          if (promotion.conversionBlockReason != null)
            _DetailRow(
              label: strings.blocked,
              value: promotion.conversionBlockReason!,
            ),
          if (preflightBlocksConvert)
            _DetailRow(
              label: strings.primaryBlockReason,
              value: preflight!.primaryBlockReason ??
                  preflight!.nextRequiredAction,
            ),
          if (promotion.reviewChecklist.isNotEmpty)
            _DetailRow(
              label: strings.checklist,
              value: promotion.reviewChecklist
                  .map((item) => '${item.ok ? 'OK' : 'BLOCK'} ${item.label}')
                  .join(' | '),
            ),
          if (promotion.conversionStatus != null)
            _DetailRow(
              label: strings.conversion,
              value: strings.statusLabel(promotion.conversionStatus!),
            ),
          if (promotion.lastSyncAt != null)
            _DetailRow(
              label: strings.lastSync,
              value: formatTimestampWithKst(
                promotion.lastSyncAt!.toIso8601String(),
              ),
            ),
          if (promotion.tracePayload.isNotEmpty)
            _DetailRow(
              label: strings.trace,
              value:
                  'promotion ${promotion.tracePayload['promotion_id'] ?? promotion.id} / dry-run ${promotion.tracePayload['source_dry_run_id'] ?? promotion.sourceDryRunTradeRunId ?? '-'} / attempt ${promotion.liveAttemptId ?? '-'} / order ${promotion.liveOrderId ?? '-'}',
            ),
          if (preflight != null) ...[
            const SizedBox(height: 10),
            _PreflightResultPanel(
              preflight: preflight!,
              strings: strings,
            ),
          ],
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                key: ValueKey('preflight-live-buy-promotion-${promotion.id}'),
                onPressed: loading ? null : onPreflight,
                icon: const Icon(Icons.fact_check_outlined, size: 18),
                label: Text(strings.preflightLiveBuy),
              ),
              OutlinedButton.icon(
                key: ValueKey('mark-reviewed-promotion-${promotion.id}'),
                onPressed: loading || !promotion.reviewRequired
                    ? null
                    : onMarkReviewed,
                icon: const Icon(Icons.visibility_outlined, size: 18),
                label: Text(strings.markReviewed),
              ),
              OutlinedButton.icon(
                key: ValueKey('dismiss-promotion-${promotion.id}'),
                onPressed: loading || promotion.isDismissed || converted
                    ? null
                    : onDismiss,
                icon: const Icon(Icons.close, size: 18),
                label: Text(strings.dismiss),
              ),
              if (promotion.canRunGuardedLive)
                FilledButton.icon(
                  key: ValueKey(
                    'convert-guarded-live-buy-promotion-${promotion.id}',
                  ),
                  onPressed: loading || !canConvert ? null : onConvert,
                  icon: const Icon(Icons.verified_user_outlined, size: 18),
                  label: Text(strings.convertViaGuardedLiveBuy),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _PreflightResultPanel extends StatelessWidget {
  const _PreflightResultPanel({
    required this.preflight,
    required this.strings,
  });

  final StrategyLiveAutoBuyPreflightResult preflight;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: ValueKey('preflight-result-promotion-${preflight.promotionId}'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Divider(color: Colors.white.withValues(alpha: 0.14)),
        Row(
          children: [
            Icon(
              preflight.isAllowed
                  ? Icons.check_circle_outline
                  : preflight.isBlocked
                      ? Icons.block
                      : Icons.info_outline,
              color: _preflightStatusColor(preflight),
              size: 18,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                strings.preflightResult,
                style: const TextStyle(fontWeight: FontWeight.w900),
              ),
            ),
            Text(
              _preflightStatusLabel(strings, preflight),
              style: TextStyle(
                color: _preflightStatusColor(preflight),
                fontWeight: FontWeight.w900,
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            _SmallBadge(text: strings.finalConfirmationRequiredShort),
            _SmallBadge(text: strings.noLiveOrderSubmitted),
            _SmallBadge(text: strings.noBrokerSubmit),
            _SmallBadge(text: strings.notAnOrder),
          ],
        ),
        if (preflight.primaryBlockReason != null)
          _DetailRow(
            label: strings.primaryBlockReason,
            value: preflight.primaryBlockReason!,
          ),
        _DetailRow(
          label: strings.estimatedNotional,
          value: _money(preflight.proposedNotionalKrw),
        ),
        _DetailRow(
          label: strings.availableCash,
          value: _money(preflight.availableCashKrw),
        ),
        if (preflight.riskFlags.isNotEmpty)
          _DetailRow(
            label: strings.riskFlags,
            value: preflight.riskFlags.join(', '),
          ),
        if (preflight.gatingNotes.isNotEmpty)
          _DetailRow(
            label: strings.gatingNotes,
            value: preflight.gatingNotes.join(' | '),
          ),
        if (preflight.checklist.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            strings.preflightChecklist,
            style: const TextStyle(
              color: Colors.white70,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 4),
          for (final item in preflight.checklist.take(12))
            Padding(
              padding: const EdgeInsets.only(bottom: 3),
              child: Text(
                '${strings.preflightChecklistStatus(item.status)} ${strings.preflightChecklistLabel(item.labelKey ?? item.key)}'
                '${item.blocking ? ' / ${strings.blocked}' : ''}',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: item.failed
                      ? Colors.orangeAccent
                      : item.warning
                          ? Colors.amberAccent
                          : Colors.white70,
                  fontSize: 12,
                ),
              ),
            ),
        ],
      ],
    );
  }
}

class _SmallBadge extends StatelessWidget {
  const _SmallBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: Colors.lightBlueAccent,
        fontSize: 11,
        fontWeight: FontWeight.w900,
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 132,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white54, fontSize: 11),
          ),
          const SizedBox(height: 2),
          Text(
            value,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 84,
            child: Text(
              label,
              style: const TextStyle(color: Colors.white54, fontSize: 12),
            ),
          ),
          Expanded(
            child: Text(
              value,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class _BadgeWrap extends StatelessWidget {
  const _BadgeWrap({required this.badges});

  final List<String> badges;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final badge in badges)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.amberAccent.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: Colors.amberAccent.withValues(alpha: 0.30),
              ),
            ),
            child: Text(
              badge,
              style: const TextStyle(
                color: Colors.amberAccent,
                fontSize: 10,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
      ],
    );
  }
}

String _preflightStatusLabel(
  AppStrings strings,
  StrategyLiveAutoBuyPreflightResult preflight,
) {
  if (preflight.isAllowed) return strings.allowed;
  if (preflight.isBlocked) return strings.blocked;
  if (preflight.requiresReview) return strings.reviewRequired;
  return strings.statusLabel(preflight.preflightStatus);
}

Color _preflightStatusColor(StrategyLiveAutoBuyPreflightResult preflight) {
  if (preflight.isAllowed) return Colors.greenAccent;
  if (preflight.isBlocked) return Colors.orangeAccent;
  return Colors.amberAccent;
}

String _number(num? value) {
  if (value == null) return '-';
  return value.toStringAsFixed(value % 1 == 0 ? 0 : 2);
}

String _money(num? value) {
  if (value == null) return '-';
  final fixed = value.toStringAsFixed(0);
  final buffer = StringBuffer();
  for (var i = 0; i < fixed.length; i += 1) {
    final remaining = fixed.length - i;
    buffer.write(fixed[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return '\u20A9${buffer.toString()}';
}
