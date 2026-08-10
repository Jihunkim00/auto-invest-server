import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';

/// User-facing Home surface. Advanced diagnostics and raw runtime controls stay
/// behind Admin; this screen only reports the effective operation state.
class HomeScreen extends StatelessWidget {
  const HomeScreen({
    super.key,
    required this.controller,
    this.onOpenAdmin,
  });

  final DashboardController controller;
  final VoidCallback? onOpenAdmin;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.load,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      controller.strings.home,
                      style: const TextStyle(
                        fontSize: 28,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                  GlobalBrokerSelector(controller: controller),
                  IconButton(
                    key: const ValueKey('home-open-admin'),
                    tooltip: 'Advanced / Admin',
                    onPressed: onOpenAdmin,
                    icon: const Icon(Icons.admin_panel_settings_outlined),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _OperationModeCard(controller: controller),
              const SizedBox(height: 12),
              _PortfolioCard(controller: controller),
              const SizedBox(height: 12),
              _PositionsCard(controller: controller),
              const SizedBox(height: 12),
              _DecisionCard(controller: controller),
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
      ),
    );
  }
}

class _OperationModeCard extends StatelessWidget {
  const _OperationModeCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final mode = controller.operationModeStatus;
    final blocked = mode.isBlocked;
    final color = blocked ? Colors.orangeAccent : Colors.lightBlueAccent;
    final detail = mode.blockingReasons.isNotEmpty
        ? mode.blockingReasons.first.message
        : mode.warnings.isNotEmpty
            ? mode.warnings.first.message
            : 'Trading decisions are reviewed through AI before any action.';

    return SectionCard(
      key: const ValueKey('home-operation-mode-card'),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(blocked ? Icons.warning_amber_outlined : Icons.shield_outlined,
              color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Operation mode',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(mode.displayLabel,
                    style: TextStyle(
                        color: color,
                        fontSize: 18,
                        fontWeight: FontWeight.w800)),
                const SizedBox(height: 4),
                Text(detail, style: const TextStyle(color: Colors.white70)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PortfolioCard extends StatelessWidget {
  const _PortfolioCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final summary = controller.selectedPortfolioSummary;
    final total =
        summary.totalMarketValue + (summary.cashKnown ? summary.cash : 0);
    final unavailable = controller.selectedPortfolioUnavailable ||
        summary.hasUnavailableKisData;
    return SectionCard(
      key: const ValueKey('home-portfolio-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Portfolio', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          if (unavailable)
            const Text('Some account data is unavailable. Refresh to retry.',
                style: TextStyle(color: Colors.orangeAccent)),
          Wrap(
            spacing: 18,
            runSpacing: 10,
            children: [
              _Metric('Value', _money(summary.currency, total)),
              _Metric(
                  'Cash',
                  summary.cashKnown
                      ? _money(summary.currency, summary.cash)
                      : 'Unknown'),
              _Metric('P/L',
                  _signedMoney(summary.currency, summary.totalUnrealizedPl)),
            ],
          ),
        ],
      ),
    );
  }
}

class _PositionsCard extends StatelessWidget {
  const _PositionsCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final positions = controller.selectedPortfolioSummary.positions
        .take(3)
        .toList(growable: false);
    return SectionCard(
      key: const ValueKey('home-positions-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Current positions',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          if (positions.isEmpty)
            const Text('No held positions loaded.',
                style: TextStyle(color: Colors.white70))
          else
            for (final position in positions)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        position.name.isEmpty
                            ? position.symbol
                            : '${position.name} (${position.symbol})',
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    Text('qty ${_number(position.qty)}',
                        style: const TextStyle(color: Colors.white70)),
                    const SizedBox(width: 12),
                    Text(
                      _signedMoney(controller.selectedPortfolioSummary.currency,
                          position.unrealizedPl),
                      style: TextStyle(
                        color: position.unrealizedPl >= 0
                            ? Colors.greenAccent
                            : Colors.redAccent,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
        ],
      ),
    );
  }
}

class _DecisionCard extends StatelessWidget {
  const _DecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final run = controller.runResult;
    final action =
        run.action.trim().isEmpty ? 'HOLD' : run.action.toUpperCase();
    final candidate = run.finalBestCandidate.trim().isEmpty
        ? 'No candidate yet'
        : run.finalBestCandidate;
    final reason = run.triggerBlockReason.trim().isEmpty
        ? run.reason.trim().isEmpty
            ? 'Ask AI for an analysis.'
            : run.reason
        : run.triggerBlockReason;
    return SectionCard(
      key: const ValueKey('home-decision-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Latest decision',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Row(
            children: [
              Text(action,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w900)),
              const SizedBox(width: 10),
              Expanded(child: Text(candidate)),
            ],
          ),
          const SizedBox(height: 4),
          Text(reason, style: const TextStyle(color: Colors.white70)),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white54)),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ],
    );
  }
}

String _money(String currency, double value) {
  final code = currency.trim().toUpperCase();
  if (code == 'KRW') return 'KRW ${value.toStringAsFixed(0)}';
  return '${code == 'USD' || code.isEmpty ? '\$' : '$code '}${value.toStringAsFixed(2)}';
}

String _signedMoney(String currency, double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${_money(currency, value)}';
}

String _number(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}
