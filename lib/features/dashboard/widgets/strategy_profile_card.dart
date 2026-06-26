import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/strategy_profile.dart';
import '../dashboard_controller.dart';

class StrategyProfileCard extends StatelessWidget {
  const StrategyProfileCard({
    super.key,
    required this.profiles,
    required this.activeProfile,
    required this.loading,
    required this.error,
    required this.applyingProfileName,
    required this.onRefresh,
    required this.onApply,
  });

  final List<StrategyProfile> profiles;
  final StrategyProfile? activeProfile;
  final bool loading;
  final String? error;
  final String? applyingProfileName;
  final Future<ActionResult> Function() onRefresh;
  final Future<ActionResult> Function(String profileName) onApply;

  @override
  Widget build(BuildContext context) {
    final active = activeProfile ??
        profiles.cast<StrategyProfile?>().firstWhere(
              (profile) => profile?.isActive == true,
              orElse: () => profiles.isEmpty ? null : profiles.first,
            );
    final statusColor =
        active?.isAggressive == true ? Colors.orangeAccent : Colors.greenAccent;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.tune_outlined, color: statusColor, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text(
                'Strategy Risk Profile',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 3),
              Text(
                active == null
                    ? 'Profile targets are not loaded yet.'
                    : '${active.displayName} · monthly target ${_pctRange(active)}',
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
            ]),
          ),
          IconButton(
            key: const ValueKey('strategy-profile-refresh'),
            tooltip: 'Refresh strategy profiles',
            onPressed: loading ? null : () => _runRefresh(context),
            icon: loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh, size: 18),
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 6, runSpacing: 6, children: [
          const _ProfileBadge(text: 'PROFILE ONLY'),
          const _ProfileBadge(text: 'NO ORDER SUBMIT'),
          const _ProfileBadge(text: 'STRATEGY TARGET'),
          if (active != null)
            _ProfileBadge(text: active.profileName.toUpperCase()),
        ]),
        if (error != null) ...[
          const SizedBox(height: 10),
          Text(
            error!,
            style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
          ),
        ],
        if (active != null) ...[
          const SizedBox(height: 12),
          _ActiveProfileSummary(profile: active),
          if (active.isAggressive) ...[
            const SizedBox(height: 10),
            const _AggressiveWarning(),
          ],
        ],
        const SizedBox(height: 12),
        _ProfileButtons(
          profiles: profiles,
          activeProfileName: active?.profileName,
          applyingProfileName: applyingProfileName,
          onApply: (profileName) => _confirmAndApply(context, profileName),
        ),
      ]),
    );
  }

  Future<void> _runRefresh(BuildContext context) async {
    final result = await onRefresh();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _confirmAndApply(
    BuildContext context,
    String profileName,
  ) async {
    final profile = profiles.firstWhere(
      (item) => item.profileName == profileName,
      orElse: () => StrategyProfile.fromJson({
        'id': 0,
        'profile_name': profileName,
        'display_name': strategyProfileLabel(profileName),
      }),
    );
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => _ProfileConfirmDialog(profile: profile),
    );
    if (confirmed != true || !context.mounted) return;
    final result = await onApply(profileName);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _ActiveProfileSummary extends StatelessWidget {
  const _ActiveProfileSummary({required this.profile});

  final StrategyProfile profile;

  @override
  Widget build(BuildContext context) {
    return Wrap(spacing: 10, runSpacing: 8, children: [
      _Metric(label: 'Monthly target', value: _pctRange(profile)),
      _Metric(
          label: 'Monthly loss cap', value: _pct(profile.monthlyMaxLossPct)),
      _Metric(label: 'Daily loss cap', value: _pct(profile.dailyMaxLossPct)),
      _Metric(
        label: 'Order limit',
        value:
            '${_pct(profile.maxOrderNotionalPct)} / ${_money(profile.maxOrderNotionalKrw)}',
      ),
      _Metric(label: 'Trades/day', value: '${profile.maxTradesPerDay}'),
      _Metric(label: 'Positions', value: '${profile.maxPositions}'),
      _Metric(label: 'Buy score', value: _score(profile.buyScoreThreshold)),
      _Metric(label: 'Sell score', value: _score(profile.sellScoreThreshold)),
      _Metric(label: 'Stop loss', value: _pct(profile.stopLossPct)),
      _Metric(label: 'Take profit', value: _pct(profile.takeProfitPct)),
      _Metric(label: 'Max hold', value: '${profile.maxHoldingDays}d'),
      _Metric(
        label: 'After loss',
        value: profile.reduceSizeAfterLoss ? 'Reduce size' : 'Keep size',
      ),
    ]);
  }
}

class _ProfileButtons extends StatelessWidget {
  const _ProfileButtons({
    required this.profiles,
    required this.activeProfileName,
    required this.applyingProfileName,
    required this.onApply,
  });

  final List<StrategyProfile> profiles;
  final String? activeProfileName;
  final String? applyingProfileName;
  final ValueChanged<String> onApply;

  @override
  Widget build(BuildContext context) {
    final available = profiles.isEmpty
        ? const ['safe', 'balanced', 'aggressive']
        : profiles.map((profile) => profile.profileName).toList();
    return Wrap(spacing: 8, runSpacing: 8, children: [
      for (final profileName in available)
        OutlinedButton(
          key: ValueKey('strategy-profile-apply-$profileName'),
          onPressed:
              applyingProfileName == null ? () => onApply(profileName) : null,
          child: applyingProfileName == profileName
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Text(
                  profileName == activeProfileName
                      ? '${strategyProfileLabel(profileName)} Active'
                      : 'Apply ${strategyProfileLabel(profileName)}',
                ),
        ),
    ]);
  }
}

class _ProfileConfirmDialog extends StatelessWidget {
  const _ProfileConfirmDialog({required this.profile});

  final StrategyProfile profile;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: const ValueKey('strategy-profile-confirm-dialog'),
      title: Text('Apply ${profile.displayName}?'),
      content: Text(
        profile.isAggressive
            ? '고수익형은 월 5% 이상을 목표로 하지만 손실 변동성이 커질 수 있습니다. 이 설정은 주문을 즉시 실행하지 않습니다. 적용할까요?'
            : 'This changes only the strategy risk profile. No order is submitted, no validation runs, and scheduler settings are not changed.',
      ),
      actions: [
        TextButton(
          key: const ValueKey('strategy-profile-confirm-cancel'),
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton(
          key: const ValueKey('strategy-profile-confirm-apply'),
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Apply Profile'),
        ),
      ],
    );
  }
}

class _AggressiveWarning extends StatelessWidget {
  const _AggressiveWarning();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.orangeAccent.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.orangeAccent.withValues(alpha: 0.32)),
      ),
      child: const Text(
        '고수익형은 월 5% 이상을 목표로 하지만 손실 변동성이 커질 수 있습니다. 월 손실 -6% 또는 일일 손실 -1.5% 도달 시 거래가 제한됩니다.',
        style: TextStyle(color: Colors.orangeAccent, height: 1.25),
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
      width: 116,
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          label,
          style: const TextStyle(color: Colors.white54, fontSize: 11),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 12,
            fontWeight: FontWeight.w800,
          ),
        ),
      ]),
    );
  }
}

class _ProfileBadge extends StatelessWidget {
  const _ProfileBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border:
            Border.all(color: Colors.lightBlueAccent.withValues(alpha: 0.34)),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.lightBlueAccent,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

String _pctRange(StrategyProfile profile) {
  return '${_pct(profile.monthlyTargetMinPct)}-${_pct(profile.monthlyTargetMaxPct)}';
}

String _pct(double value) {
  final pct = value * 100;
  final text =
      pct.abs() >= 10 ? pct.toStringAsFixed(0) : pct.toStringAsFixed(1);
  return '$text%';
}

String _score(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(1);
}

String _money(double value) {
  return 'KRW ${_groupDigits(value.round().toString())}';
}

String _groupDigits(String value) {
  final buffer = StringBuffer();
  for (var i = 0; i < value.length; i += 1) {
    final fromEnd = value.length - i;
    buffer.write(value[i]);
    if (fromEnd > 1 && fromEnd % 3 == 1) buffer.write(',');
  }
  return buffer.toString();
}
