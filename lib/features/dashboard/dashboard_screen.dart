import 'package:flutter/material.dart';

import '../../core/utils/timestamp_formatter.dart';
import '../../core/widgets/section_card.dart';
import '../../core/widgets/status_badge.dart';
import '../../models/scheduler_status.dart';
import '../../models/trading_run.dart';
import 'dashboard_controller.dart';
import 'widgets/automation_event_timeline_card.dart';
import 'widgets/automation_runtime_monitor_card.dart';
import 'widgets/broker_context_controls.dart';
import 'widgets/operation_rehearsal_panel.dart';
import 'widgets/portfolio_snapshot_section.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
    this.onReviewPosition,
    this.onOpenSettings,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;
  final VoidCallback? onOpenSettings;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: RefreshIndicator(
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
                            fontSize: 28, fontWeight: FontWeight.w700),
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
                _OperationalReadinessCard(
                  controller: controller,
                  onOpenSettings: onOpenSettings,
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
