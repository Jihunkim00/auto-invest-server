import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../models/position_exit_review.dart';
import '../../dashboard/dashboard_controller.dart';

class PositionExitReviewPanel extends StatelessWidget {
  const PositionExitReviewPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final review = controller.positionExitReview;
        final loading = controller.positionExitReviewLoading ||
            controller.positionSellPreflightLoading;
        final preflight = controller.latestPositionSellPreflight;
        return Container(
          key: const ValueKey('position-exit-review-panel'),
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.22),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.inventory_2_outlined,
                      color: Colors.tealAccent, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.positionExitReview,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          review == null
                              ? strings.statusNotLoaded
                              : '${review.positions.length} ${strings.heldPositions} / ${_money(review.totalPositionValue, review.market)}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('refresh-position-exit-review-button'),
                    tooltip: strings.refreshPositions,
                    onPressed: loading
                        ? null
                        : () => _refresh(context, showSnack: true),
                    icon: const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _BadgeWrap(labels: [
                strings.preflightOnly,
                strings.noLiveOrderSubmitted,
                strings.noBrokerSubmitDisplay,
                strings.finalConfirmationRequiredDisplay,
              ]),
              if (controller.positionExitReviewError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.positionExitReviewError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (controller.positionSellPreflightError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.positionSellPreflightError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              if (loading && review == null) ...[
                const SizedBox(height: 12),
                const LinearProgressIndicator(),
              ],
              const SizedBox(height: 12),
              if (preflight != null)
                _PreflightResult(
                  result: preflight,
                  strings: strings,
                  onBack: controller.clearPositionSellPreflight,
                )
              else if (review == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else if (review.positions.isEmpty) ...[
                _HeldPositionsHeader(strings: strings),
                const SizedBox(height: 8),
                _EmptyLine(text: strings.noHeldPositions),
              ] else ...[
                _HeldPositionsHeader(strings: strings),
                const SizedBox(height: 8),
                _ReviewTotals(review: review, strings: strings),
                const SizedBox(height: 10),
                for (final position in review.positions) ...[
                  _PositionRow(
                    position: position,
                    strings: strings,
                    loading: loading,
                    onPreflight: () => _runPreflight(context, position),
                  ),
                  const SizedBox(height: 8),
                ],
              ],
            ],
          ),
        );
      },
    );
  }

  Future<void> _refresh(
    BuildContext context, {
    required bool showSnack,
  }) async {
    final result = await controller.refreshPositionExitReview();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _runPreflight(
    BuildContext context,
    PositionExitReviewItem position,
  ) async {
    final result = await controller.runPositionSellPreflight(position);
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _HeldPositionsHeader extends StatelessWidget {
  const _HeldPositionsHeader({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Text(
      strings.heldPositions,
      key: const ValueKey('position-exit-review-held-positions-section'),
      style: const TextStyle(
        color: Colors.white,
        fontWeight: FontWeight.w900,
      ),
    );
  }
}

class _ReviewTotals extends StatelessWidget {
  const _ReviewTotals({required this.review, required this.strings});

  final PositionExitReview review;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 10,
      runSpacing: 8,
      children: [
        _MetricChip(
          label: strings.marketValue,
          value: _money(review.totalPositionValue, review.market),
        ),
        _MetricChip(
          label: strings.unrealizedPl,
          value:
              '${_money(review.totalUnrealizedPl, review.market)} / ${_percent(review.totalUnrealizedPlPct)}',
        ),
      ],
    );
  }
}

class _PositionRow extends StatelessWidget {
  const _PositionRow({
    required this.position,
    required this.strings,
    required this.loading,
    required this.onPreflight,
  });

  final PositionExitReviewItem position;
  final AppStrings strings;
  final bool loading;
  final VoidCallback onPreflight;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: ValueKey('position-exit-review-${position.symbol}'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      position.displayName,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${strings.statusLabel(position.exitReviewStatus)} / ${position.primaryRiskNote}',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              OutlinedButton.icon(
                key: const ValueKey(
                  'position-exit-review-sell-preflight-button',
                ),
                onPressed: loading || position.availableQuantity <= 0
                    ? null
                    : onPreflight,
                icon: const Icon(Icons.fact_check_outlined, size: 18),
                label: Text(strings.sellPreflight),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 7,
            children: [
              _MetricChip(
                label: strings.quantityHeld,
                value: _number(position.quantity),
              ),
              _MetricChip(
                label: strings.availableQuantity,
                value: _number(position.availableQuantity),
              ),
              _MetricChip(
                label: strings.averageEntryPrice,
                value: _money(position.averagePrice, position.market),
              ),
              _MetricChip(
                label: strings.currentPriceLabel,
                value: _money(position.currentPrice, position.market),
              ),
              _MetricChip(
                label: strings.marketValue,
                value: _money(position.currentValue, position.market),
              ),
              _MetricChip(
                label: strings.unrealizedPl,
                value:
                    '${_money(position.unrealizedPl, position.market)} / ${_percent(position.unrealizedPlPct)}',
              ),
              _MetricChip(
                label: strings.stopLossCondition,
                value: strings.booleanLabel(position.stopLossTriggered),
              ),
              _MetricChip(
                label: strings.takeProfitCondition,
                value: strings.booleanLabel(position.takeProfitTriggered),
              ),
            ],
          ),
          if (position.riskFlags.isNotEmpty) ...[
            const SizedBox(height: 8),
            _SmallText(
              label: strings.riskFlags,
              value: position.riskFlags.join(', '),
            ),
          ],
        ],
      ),
    );
  }
}

class _PreflightResult extends StatelessWidget {
  const _PreflightResult({
    required this.result,
    required this.strings,
    required this.onBack,
  });

  final PositionSellPreflightResult result;
  final AppStrings strings;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final statusColor = result.isAllowed
        ? Colors.greenAccent
        : result.isBlocked
            ? Colors.redAccent
            : Colors.orangeAccent;
    return KeyedSubtree(
      key: const ValueKey('sell-preflight-result-panel'),
      child: Container(
        key: const ValueKey('position-exit-review-preflight-result-panel'),
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: statusColor.withValues(alpha: 0.35)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.verified_user_outlined,
                    color: statusColor, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        strings.sellPreflight,
                        style: TextStyle(
                          color: statusColor,
                          fontSize: 16,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        strings.statusLabel(result.preflightStatus),
                        style: TextStyle(
                          color: statusColor.withValues(alpha: 0.82),
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                ),
                TextButton.icon(
                  key: const ValueKey('back-to-positions-button'),
                  onPressed: onBack,
                  icon: const Icon(Icons.arrow_back, size: 18),
                  label: Text(strings.backToPositions),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _BadgeWrap(labels: [
              strings.noLiveOrderSubmitted,
              strings.noBrokerSubmitDisplay,
              strings.finalConfirmationRequiredDisplay,
            ]),
            const SizedBox(height: 12),
            Wrap(
              spacing: 12,
              runSpacing: 7,
              children: [
                _MetricChip(label: strings.symbolLabel, value: result.symbol),
                _MetricChip(
                  label: strings.requestedQuantity,
                  value: _number(result.requestedQuantity),
                ),
                _MetricChip(
                  label: strings.availableQuantity,
                  value: _number(result.availableQuantity),
                ),
                _MetricChip(
                  label: strings.estimatedSellNotional,
                  value: _money(result.estimatedSellNotional, result.market),
                ),
                _MetricChip(
                  label: strings.unrealizedPl,
                  value:
                      '${_money(result.unrealizedPl, result.market)} / ${_percent(result.unrealizedPlPct)}',
                ),
                _MetricChip(
                  label: strings.stopLossCondition,
                  value: strings.booleanLabel(result.stopLossTriggered),
                ),
                _MetricChip(
                  label: strings.takeProfitCondition,
                  value: strings.booleanLabel(result.takeProfitTriggered),
                ),
              ],
            ),
            if (result.primaryBlockReason != null) ...[
              const SizedBox(height: 10),
              Container(
                key: const ValueKey(
                  'position-exit-review-primary-block-reason',
                ),
                width: double.infinity,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      strings.primaryBlockReason,
                      style: const TextStyle(
                        color: Colors.white54,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      result.primaryBlockReason!,
                      style: const TextStyle(color: Colors.orangeAccent),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 10),
            _SmallText(
              label: strings.nextRequiredAction,
              value: result.nextRequiredAction,
            ),
            if (result.riskFlags.isNotEmpty) ...[
              const SizedBox(height: 8),
              _SmallText(
                label: strings.riskFlags,
                value: result.riskFlags.join(', '),
              ),
            ],
            if (result.gatingNotes.isNotEmpty) ...[
              const SizedBox(height: 8),
              _SmallText(
                label: strings.gatingNotes,
                value: result.gatingNotes.join(' | '),
              ),
            ],
            const SizedBox(height: 10),
            Text(
              strings.preflightChecklist,
              key: const ValueKey('position-exit-review-checklist'),
              style: const TextStyle(
                color: Colors.white70,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 7),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final item in result.checklist)
                  _ChecklistChip(item: item, strings: strings),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ChecklistChip extends StatelessWidget {
  const _ChecklistChip({required this.item, required this.strings});

  final PositionSellPreflightChecklistItem item;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = item.status == 'pass'
        ? Colors.greenAccent
        : item.status == 'fail'
            ? Colors.redAccent
            : Colors.orangeAccent;
    return Container(
      constraints: const BoxConstraints(maxWidth: 280),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '${strings.preflightChecklistStatus(item.status)}: ${item.displayLabel ?? strings.preflightChecklistLabel(item.labelKey ?? item.key)}',
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w900,
            ),
          ),
          if (item.detail != null) ...[
            const SizedBox(height: 3),
            Text(
              item.detail!,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white70, fontSize: 12),
            ),
          ],
        ],
      ),
    );
  }
}

class _MetricChip extends StatelessWidget {
  const _MetricChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minWidth: 112, maxWidth: 220),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.22),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white54, fontSize: 11),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ],
      ),
    );
  }
}

class _BadgeWrap extends StatelessWidget {
  const _BadgeWrap({required this.labels});

  final List<String> labels;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (final label in labels)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
            decoration: BoxDecoration(
              color: Colors.tealAccent.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: Colors.tealAccent.withValues(alpha: 0.28),
              ),
            ),
            child: Text(
              label,
              style: const TextStyle(
                color: Colors.tealAccent,
                fontSize: 10,
                fontWeight: FontWeight.w900,
              ),
            ),
          ),
      ],
    );
  }
}

class _SmallText extends StatelessWidget {
  const _SmallText({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: '$label: ',
            style: const TextStyle(
              color: Colors.white54,
              fontWeight: FontWeight.w700,
            ),
          ),
          TextSpan(
            text: value,
            style: const TextStyle(color: Colors.white70),
          ),
        ],
      ),
    );
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(color: Colors.white70));
  }
}

String _number(num? value) {
  if (value == null) return '-';
  return value.toStringAsFixed(value % 1 == 0 ? 0 : 2);
}

String _percent(num? value) {
  if (value == null) return '-';
  final percent = value * 100;
  final sign = percent > 0 ? '+' : '';
  return '$sign${percent.toStringAsFixed(2)}%';
}

String _money(num? value, String market) {
  if (value == null) return '-';
  final decimals = market.toUpperCase() == 'KR' ? 0 : 2;
  final sign = value < 0 ? '-' : '';
  final currency = market.toUpperCase() == 'KR' ? 'KRW' : 'USD';
  return '$sign$currency ${_grouped(value.abs(), decimals: decimals)}';
}

String _grouped(num value, {required int decimals}) {
  final fixed = value.toStringAsFixed(decimals);
  final parts = fixed.split('.');
  final whole = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i += 1) {
    final remaining = whole.length - i;
    buffer.write(whole[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  if (decimals == 0) return buffer.toString();
  return '${buffer.toString()}.${parts.last}';
}
