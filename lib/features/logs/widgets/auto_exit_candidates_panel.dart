import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/auto_exit_candidate.dart';
import '../../dashboard/dashboard_controller.dart';

class AutoExitCandidatesPanel extends StatelessWidget {
  const AutoExitCandidatesPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final payload = controller.autoExitCandidates;
        final loading = controller.autoExitCandidatesLoading ||
            controller.positionSellPreflightLoading;
        return Container(
          key: const ValueKey('auto-exit-candidates-panel'),
          width: double.infinity,
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
                  const Icon(
                    Icons.manage_search_outlined,
                    color: Colors.amberAccent,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.autoExitCandidates,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          payload == null
                              ? strings.statusNotLoaded
                              : '${strings.positionMonitoring} / ${strings.brokerName(payload.provider)} / ${payload.market} / ${_timestamp(payload.generatedAt)}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('auto-exit-candidates-refresh-button'),
                    tooltip: strings.refreshExitCandidates,
                    onPressed: loading
                        ? null
                        : () => _refresh(context, showSnack: true),
                    icon: loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _BadgeWrap(labels: [
                strings.operatorReadOnly,
                strings.operatorNoLiveOrders,
                strings.noBrokerSubmitDisplay,
              ]),
              if (controller.autoExitCandidatesError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.autoExitCandidatesError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (payload == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else ...[
                _SummaryGrid(payload: payload, strings: strings),
                const SizedBox(height: 12),
                if (payload.candidates.isEmpty)
                  _EmptyLine(text: strings.none)
                else
                  for (final candidate in payload.candidates.take(8)) ...[
                    _CandidateTile(
                      candidate: candidate,
                      strings: strings,
                      loading: loading,
                      onPreflight: () => _runPreflight(context, candidate),
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
    final result = await controller.refreshAutoExitCandidates();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _runPreflight(
    BuildContext context,
    AutoExitCandidate candidate,
  ) async {
    final result =
        await controller.runAutoExitCandidateSellPreflight(candidate);
    if (!context.mounted) return;
    _snack(context, result.message);
  }

  void _snack(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }
}

class _SummaryGrid extends StatelessWidget {
  const _SummaryGrid({required this.payload, required this.strings});

  final AutoExitCandidates payload;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final summary = payload.summary;
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MetricTile(
          label: strings.totalCandidates,
          value: '${summary.candidateCount}',
          valueColor: Colors.white,
        ),
        _MetricTile(
          label: strings.critical,
          value: '${summary.criticalCount}',
          valueColor:
              summary.criticalCount > 0 ? Colors.redAccent : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.stopLossCandidate,
          value: '${summary.stopLossCount}',
          valueColor: summary.stopLossCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.takeProfitCandidate,
          value: '${summary.takeProfitCount}',
          valueColor: summary.takeProfitCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.syncRequired,
          value: '${summary.syncRequiredCount}',
          valueColor: summary.syncRequiredCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
      ],
    );
  }
}

class _CandidateTile extends StatelessWidget {
  const _CandidateTile({
    required this.candidate,
    required this.strings,
    required this.loading,
    required this.onPreflight,
  });

  final AutoExitCandidate candidate;
  final AppStrings strings;
  final bool loading;
  final VoidCallback onPreflight;

  @override
  Widget build(BuildContext context) {
    final severityColor = _severityColor(candidate.severity);
    final pl = candidate.unrealizedPlPct == null
        ? strings.calculationIncomplete
        : '${_money(candidate.unrealizedPl, candidate.market)} / ${_percent(candidate.unrealizedPlPct)}';
    return Container(
      key: ValueKey('auto-exit-candidate-${candidate.candidateId}'),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.045),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: severityColor.withValues(alpha: 0.30)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(
                candidate.symbol,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w900,
                ),
              ),
              _StatusPill(
                label: strings.autoExitCandidateTypeLabel(
                  candidate.candidateType,
                ),
                color: Colors.lightBlueAccent,
              ),
              _StatusPill(
                label: strings.autoExitSeverityLabel(candidate.severity),
                color: severityColor,
              ),
              _StatusPill(
                label: pl,
                color: candidate.unrealizedPl == null
                    ? Colors.white54
                    : candidate.unrealizedPl! < 0
                        ? Colors.redAccent
                        : Colors.greenAccent,
              ),
            ],
          ),
          const SizedBox(height: 8),
          _LabeledText(
              label: strings.primaryReason, value: candidate.primaryReason),
          const SizedBox(height: 5),
          _LabeledText(
            label: strings.nextSafeAction,
            value: candidate.nextSafeAction,
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  candidate.canRunSellPreflight
                      ? strings.runSellPreflight
                      : _disabledReason(candidate, strings),
                  style: const TextStyle(color: Colors.white60, fontSize: 12),
                ),
              ),
              FilledButton.icon(
                key: ValueKey(
                  'auto-exit-candidate-sell-preflight-${candidate.symbol}',
                ),
                onPressed: loading || !candidate.canRunSellPreflight
                    ? null
                    : onPreflight,
                icon: const Icon(Icons.fact_check_outlined, size: 18),
                label: Text(strings.runSellPreflight),
              ),
            ],
          ),
          ExpansionTile(
            key: ValueKey('auto-exit-candidate-details-${candidate.symbol}'),
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: Text(
              strings.detailsLabel,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            children: [
              _DetailLine(
                label: strings.riskFlags,
                value: _join(candidate.riskFlags, strings.none),
              ),
              _DetailLine(
                label: strings.gatingNotes,
                value: _join(candidate.gatingNotes, strings.none),
              ),
              _DetailLine(
                label: strings.thresholdValues,
                value:
                    '${strings.stopLossCondition}: ${_threshold(candidate.stopLossThresholdPct)} / ${strings.takeProfitCondition}: ${_threshold(candidate.takeProfitThresholdPct)}',
              ),
              _DetailLine(
                label: strings.relatedReferences,
                value:
                    'buy=${candidate.relatedBuyOrderId ?? '-'} / lifecycle=${candidate.relatedLifecycleId ?? '-'}',
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.label,
    required this.value,
    required this.valueColor,
  });

  final String label;
  final String value;
  final Color valueColor;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 128, maxWidth: 190),
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontSize: 12, color: Colors.white70),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w900,
              color: valueColor,
            ),
          ),
        ]),
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
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
            ),
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w800,
                letterSpacing: 0,
              ),
            ),
          ),
      ],
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.40)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
          letterSpacing: 0,
        ),
      ),
    );
  }
}

class _LabeledText extends StatelessWidget {
  const _LabeledText({required this.label, required this.value});

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
              color: Colors.white,
              fontWeight: FontWeight.w800,
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

class _DetailLine extends StatelessWidget {
  const _DetailLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: _LabeledText(label: label, value: value),
    );
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text, style: const TextStyle(color: Colors.white60));
  }
}

Color _severityColor(String severity) {
  switch (severity) {
    case 'critical':
      return Colors.redAccent;
    case 'warning':
      return Colors.orangeAccent;
    default:
      return Colors.lightBlueAccent;
  }
}

String _disabledReason(AutoExitCandidate candidate, AppStrings strings) {
  if (candidate.syncRequired) return strings.syncRequired;
  if (candidate.openSellOrderConflict) return strings.duplicateSellOrder;
  return candidate.primaryReason;
}

String _join(List<String> values, String emptyText) {
  if (values.isEmpty) return emptyText;
  return values.take(4).join(', ');
}

String _threshold(double? value) {
  if (value == null) return '-';
  return '${value.toStringAsFixed(2)}%';
}

String _percent(double? value) {
  if (value == null) return '-';
  return '${(value * 100).toStringAsFixed(2)}%';
}

String _number(double? value) {
  if (value == null) return '-';
  if (value.abs() >= 1000) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2).replaceFirst(RegExp(r'\.?0+$'), '');
}

String _money(double? value, String market) {
  if (value == null) return '-';
  final currency = market.toUpperCase() == 'US' ? 'USD' : 'KRW';
  final prefix = currency == 'KRW' ? '₩' : r'$';
  return '$prefix${_number(value)}';
}

String _timestamp(DateTime? value) {
  if (value == null) return '-';
  return formatTimestampWithKst(value.toIso8601String());
}
