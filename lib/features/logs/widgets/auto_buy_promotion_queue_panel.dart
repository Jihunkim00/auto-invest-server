import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/strategy_auto_buy_promotion.dart';
import '../../dashboard/dashboard_controller.dart';

class AutoBuyPromotionQueuePanel extends StatelessWidget {
  const AutoBuyPromotionQueuePanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final loading = controller.strategyAutoBuyPromotionsLoading ||
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
                          const Text(
                            'Auto Buy Promotion Queue',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            '${items.length} promotion trace${items.length == 1 ? '' : 's'}',
                            style: const TextStyle(color: Colors.white70),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      key: const ValueKey('refresh-promotions-button'),
                      tooltip: 'Refresh Promotions',
                      onPressed: loading
                          ? null
                          : () => _refresh(context, showSnack: true),
                      icon: const Icon(Icons.refresh),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                const _BadgeWrap(
                  badges: [
                    'PROMOTION ONLY',
                    'NO LIVE SCHEDULER',
                    'NO VALIDATION IN SCHEDULER',
                    'NO BROKER SUBMIT IN SCHEDULER',
                    'OPERATOR CONFIRM REQUIRED',
                  ],
                ),
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
                      label: const Text('Refresh Promotions'),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                if (items.isEmpty)
                  const Text(
                    'No promotion traces.',
                    style: TextStyle(color: Colors.white70),
                  )
                else
                  Column(
                    children: [
                      for (final item in items)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 10),
                          child: _PromotionTile(
                            promotion: item,
                            loading: loading,
                            liveReady: controller
                                    .strategyAutoBuyOperationsStatus
                                    ?.liveReadiness
                                    .ready ==
                                true,
                            onAcknowledge: () => _acknowledge(context, item),
                            onDismiss: () => _dismiss(context, item),
                            onRunLive: () => _confirmLiveRun(context, item),
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

  Future<void> _acknowledge(
    BuildContext context,
    StrategyAutoBuyPromotion promotion,
  ) async {
    final result = await controller.acknowledgeStrategyAutoBuyPromotion(
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

  Future<void> _confirmLiveRun(
    BuildContext context,
    StrategyAutoBuyPromotion promotion,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        key: const ValueKey('promotion-live-confirm-dialog'),
        title: const Text('Confirm Guarded Live Auto Buy'),
        content: Text(
          'Run guarded live auto buy for ${promotion.symbol ?? '-'} using the existing one-shot path.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(true),
            icon: const Icon(Icons.verified_user_outlined),
            label: const Text('Run Guarded Live Auto Buy'),
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
    required this.loading,
    required this.liveReady,
    required this.onAcknowledge,
    required this.onDismiss,
    required this.onRunLive,
  });

  final StrategyAutoBuyPromotion promotion;
  final bool loading;
  final bool liveReady;
  final VoidCallback onAcknowledge;
  final VoidCallback onDismiss;
  final VoidCallback onRunLive;

  @override
  Widget build(BuildContext context) {
    final score = promotion.finalScore ?? promotion.buyScore;
    final canRun = promotion.canRunGuardedLive && liveReady;
    final converted = promotion.isConverted;
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
                converted ? 'CONVERTED' : promotion.status.toUpperCase(),
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
              _Metric(label: 'Score', value: _number(score)),
              _Metric(
                label: 'Notional',
                value: _money(promotion.simulatedNotionalKrw),
              ),
              _Metric(
                label: 'Qty',
                value: _number(promotion.simulatedQuantity),
              ),
              _Metric(
                label: 'Price',
                value: _money(promotion.simulatedPrice),
              ),
              _Metric(
                label: 'Expires',
                value: promotion.expiresAt == null
                    ? '-'
                    : formatTimestampWithKst(
                        promotion.expiresAt!.toIso8601String(),
                      ),
              ),
              if (promotion.liveAttemptId != null)
                _Metric(
                  label: 'Live attempt',
                  value: promotion.liveAttemptId.toString(),
                ),
              if (promotion.liveOrderId != null)
                _Metric(
                  label: 'Order',
                  value: promotion.liveOrderId.toString(),
                ),
              if (promotion.lastSyncStatus != null)
                _Metric(
                  label: 'Sync',
                  value: promotion.lastSyncStatus!.toUpperCase(),
                ),
            ],
          ),
          const SizedBox(height: 8),
          _DetailRow(
            label: 'Reason',
            value: promotion.promotionReason ?? promotion.blockReason ?? '-',
          ),
          _DetailRow(
            label: 'Dry-run IDs',
            value:
                'signal ${promotion.sourceDryRunSignalId ?? '-'} / run ${promotion.sourceDryRunTradeRunId ?? '-'} / order ${promotion.sourceDryRunOrderId ?? '-'}',
          ),
          if (promotion.riskFlags.isNotEmpty)
            _DetailRow(
                label: 'Risk flags', value: promotion.riskFlags.join(', ')),
          if (promotion.gatingNotes.isNotEmpty)
            _DetailRow(
                label: 'Gates', value: promotion.gatingNotes.join(' | ')),
          if (promotion.conversionStatus != null)
            _DetailRow(
              label: 'Conversion',
              value: promotion.conversionStatus!,
            ),
          if (promotion.lastSyncAt != null)
            _DetailRow(
              label: 'Last sync',
              value: formatTimestampWithKst(
                promotion.lastSyncAt!.toIso8601String(),
              ),
            ),
          if (promotion.tracePayload.isNotEmpty)
            _DetailRow(
              label: 'Trace',
              value:
                  'promotion ${promotion.tracePayload['promotion_id'] ?? promotion.id} / dry-run ${promotion.tracePayload['source_dry_run_id'] ?? promotion.sourceDryRunTradeRunId ?? '-'} / attempt ${promotion.liveAttemptId ?? '-'} / order ${promotion.liveOrderId ?? '-'}',
            ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton.icon(
                key: ValueKey('acknowledge-promotion-${promotion.id}'),
                onPressed: loading || promotion.status != 'pending'
                    ? null
                    : onAcknowledge,
                icon: const Icon(Icons.visibility_outlined, size: 18),
                label: const Text('Acknowledge'),
              ),
              OutlinedButton.icon(
                key: ValueKey('dismiss-promotion-${promotion.id}'),
                onPressed: loading || promotion.status == 'dismissed'
                    ? null
                    : onDismiss,
                icon: const Icon(Icons.close, size: 18),
                label: const Text('Dismiss'),
              ),
              if (promotion.status == 'pending')
                FilledButton.icon(
                  key: ValueKey('run-live-auto-buy-promotion-${promotion.id}'),
                  onPressed: loading || !canRun ? null : onRunLive,
                  icon: const Icon(Icons.verified_user_outlined, size: 18),
                  label: const Text('Run Guarded Live Auto Buy'),
                ),
            ],
          ),
        ],
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
