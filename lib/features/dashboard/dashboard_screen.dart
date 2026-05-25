import 'package:flutter/material.dart';

import '../../core/i18n/app_strings.dart';
import '../../core/utils/timestamp_formatter.dart';
import '../../core/widgets/language_toggle_chip.dart';
import '../../core/widgets/section_card.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/trading_run.dart';
import 'dashboard_controller.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/portfolio_snapshot_section.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
    this.onReviewPosition,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: RefreshIndicator(
            onRefresh: controller.load,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        AppStrings.t(AppTextKey.autoInvest, controller.uiLanguage),
                        style: TextStyle(
                            fontSize: 28, fontWeight: FontWeight.w700),
                      ),
                    ),
                    Row(children:[LanguageToggleChip(isKorean: controller.isKoreanUi, onTap: controller.toggleUiLanguage), const SizedBox(width: 8), GlobalBrokerSelector(controller: controller)]),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  controller.selectedProvider == SelectedProvider.kis
                      ? AppStrings.t(AppTextKey.kisSubtitle, controller.uiLanguage)
                      : AppStrings.t(AppTextKey.alpacaSubtitle, controller.uiLanguage),
                  style: const TextStyle(color: Color(0xFF6B7280)),
                ),
                const SizedBox(height: 14),
                _SafetySummary(controller: controller),
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
        );
      },
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
              color: safety.kisEnabled ? Colors.greenAccent : Color(0xFF6B7280),
            ),
            _SafetyPill(
              text: safety.kisRealOrderEnabled
                  ? 'KIS real orders allowed'
                  : 'KIS real orders disabled',
              color: safety.kisRealOrderEnabled
                  ? Colors.redAccent
                  : Color(0xFF6B7280),
            ),
            _SafetyPill(
              text: safety.marketOpen ? 'KR market open' : 'KR market closed',
              color: safety.marketOpen ? Colors.greenAccent : Color(0xFF6B7280),
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
                  : Color(0xFF6B7280),
            ),
          ],
        ]),
      ]),
    );
  }
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
              style: TextStyle(color: Color(0xFF6B7280)))
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
        style: const TextStyle(color: Color(0xFF6B7280)),
      ),
    );
  }
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
          child: Text(label, style: const TextStyle(color: Color(0xFF9CA3AF))),
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
