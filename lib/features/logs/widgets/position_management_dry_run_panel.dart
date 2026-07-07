import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../models/auto_exit_candidate.dart';
import '../../../models/position_management_dry_run.dart';
import '../../dashboard/dashboard_controller.dart';

class PositionManagementDryRunPanel extends StatelessWidget {
  const PositionManagementDryRunPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        final payload = controller.positionManagementDryRun;
        final loading = controller.positionManagementDryRunLoading;
        return Container(
          key: const ValueKey('position-management-dry-run-panel'),
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
                    Icons.account_tree_outlined,
                    color: Colors.lightGreenAccent,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.positionManagementDryRun,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          payload == null
                              ? strings.statusNotLoaded
                              : '${strings.positionsFirst} / ${strings.brokerName(payload.provider)} / ${payload.market} / ${_timestamp(payload.generatedAt)}',
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey(
                      'position-management-dry-run-refresh-button',
                    ),
                    onPressed: loading
                        ? null
                        : () => _refresh(context, showSnack: true),
                    icon: loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.refresh, size: 18),
                    label: Text(strings.refresh),
                  ),
                  FilledButton.icon(
                    key: const ValueKey(
                      'position-management-dry-run-run-once-button',
                    ),
                    onPressed: loading ? null : () => _runOnce(context),
                    icon: const Icon(Icons.play_arrow_outlined, size: 18),
                    label: Text(strings.runPositionManagementDryRunOnce),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _BadgeWrap(labels: [
                strings.dryRunOnly,
                strings.operatorNoLiveOrders,
                strings.noBrokerSubmitDisplay,
                strings.noSellExecution,
              ]),
              if (controller.positionManagementDryRunError != null) ...[
                const SizedBox(height: 10),
                Text(
                  controller.positionManagementDryRunError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
              ],
              const SizedBox(height: 12),
              if (payload == null)
                _EmptyLine(text: strings.statusNotLoaded)
              else ...[
                _SummaryGrid(payload: payload, strings: strings),
                const SizedBox(height: 12),
                _LatestRun(payload: payload, strings: strings),
                const SizedBox(height: 10),
                if (payload.candidates.isEmpty)
                  _EmptyLine(text: strings.none)
                else
                  ExpansionTile(
                    key: const ValueKey(
                      'position-management-dry-run-candidates-expansion',
                    ),
                    tilePadding: EdgeInsets.zero,
                    childrenPadding: EdgeInsets.zero,
                    title: Text(
                      strings.autoExitCandidateCheck,
                      style: const TextStyle(fontWeight: FontWeight.w800),
                    ),
                    children: [
                      for (final candidate in payload.candidates.take(6)) ...[
                        _CandidatePreview(
                          candidate: candidate,
                          strings: strings,
                        ),
                        const SizedBox(height: 8),
                      ],
                    ],
                  ),
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
    final result = await controller.refreshPositionManagementDryRun();
    if (!context.mounted || !showSnack) return;
    _snack(context, result.message);
  }

  Future<void> _runOnce(BuildContext context) async {
    final result = await controller.runPositionManagementDryRunOnce();
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

  final PositionManagementDryRun payload;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        _MetricTile(
          label: strings.positionsChecked,
          value: '${payload.positionsChecked}',
          valueColor: Colors.white,
        ),
        _MetricTile(
          label: strings.exitCandidates,
          value: '${payload.exitCandidateCount}',
          valueColor: payload.exitCandidateCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.criticalCandidates,
          value: '${payload.criticalCandidateCount}',
          valueColor: payload.criticalCandidateCount > 0
              ? Colors.redAccent
              : Colors.greenAccent,
        ),
        _MetricTile(
          label: strings.syncRequired,
          value: '${payload.syncRequiredCount}',
          valueColor: payload.syncRequiredCount > 0
              ? Colors.orangeAccent
              : Colors.greenAccent,
        ),
      ],
    );
  }
}

class _LatestRun extends StatelessWidget {
  const _LatestRun({required this.payload, required this.strings});

  final PositionManagementDryRun payload;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      key: const ValueKey('position-management-dry-run-details-expansion'),
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      initiallyExpanded: true,
      title: Text(
        strings.latestRunResult,
        style: const TextStyle(fontWeight: FontWeight.w800),
      ),
      subtitle: Text(
        '${strings.status}: ${payload.resultStatus}',
        style: const TextStyle(color: Colors.white70),
      ),
      children: [
        _DetailLine(
          label: strings.primaryReason,
          value: payload.primaryReason ?? strings.none,
        ),
        _DetailLine(
          label: strings.riskFlags,
          value: _join(payload.riskFlags, strings.none),
        ),
        _DetailLine(
          label: strings.gatingNotes,
          value: _join(payload.gatingNotes, strings.none),
        ),
        _DetailLine(
          label: strings.nextSafeAction,
          value: _join(payload.nextSafeActions, strings.none),
        ),
        _DetailLine(
          label: strings.autoExitCandidateCheck,
          value:
              '${strings.sellPreflight}: ${payload.simulatedSellPreflightCount} / ${strings.blocked}: ${payload.blockedPreflightCount}',
        ),
      ],
    );
  }
}

class _CandidatePreview extends StatelessWidget {
  const _CandidatePreview({required this.candidate, required this.strings});

  final AutoExitCandidate candidate;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: ValueKey('position-management-candidate-${candidate.candidateId}'),
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.045),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(
            candidate.symbol,
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900),
          ),
          _StatusPill(
            label: strings.autoExitCandidateTypeLabel(candidate.candidateType),
            color: Colors.lightBlueAccent,
          ),
          _StatusPill(
            label: strings.autoExitSeverityLabel(candidate.severity),
            color: _severityColor(candidate.severity),
          ),
          _StatusPill(
            label: candidate.actionHint,
            color: Colors.white70,
          ),
          Text(
            _pl(candidate, strings),
            style: const TextStyle(color: Colors.white70),
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

class _DetailLine extends StatelessWidget {
  const _DetailLine({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text.rich(
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
      ),
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

String _join(List<String> values, String emptyText) {
  if (values.isEmpty) return emptyText;
  return values.take(4).join(', ');
}

String _pl(AutoExitCandidate candidate, AppStrings strings) {
  if (candidate.unrealizedPlPct == null) return strings.unrealizedPl;
  final amount = candidate.unrealizedPl == null
      ? '-'
      : '${candidate.market.toUpperCase() == 'US' ? r'$' : '₩'}${candidate.unrealizedPl!.toStringAsFixed(0)}';
  final pct = '${(candidate.unrealizedPlPct! * 100).toStringAsFixed(2)}%';
  return '${strings.unrealizedPl}: $amount / $pct';
}

String _timestamp(DateTime? value) {
  if (value == null) return '-';
  return formatTimestampWithKst(value.toIso8601String());
}
