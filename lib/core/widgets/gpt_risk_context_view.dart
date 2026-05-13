import 'package:flutter/material.dart';

import '../../models/gpt_risk_context.dart';

class GptRiskContextSummaryBadges extends StatelessWidget {
  const GptRiskContextSummaryBadges({
    super.key,
    required this.context,
    this.compact = false,
  });

  final GptRiskContext context;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final badges = <_RiskBadgeData>[
      if (this.context.eventRiskLevel != null)
        _RiskBadgeData('Event Risk ${this.context.eventRiskLevel}',
            _riskColor(this.context.eventRiskLevel)),
      if (this.context.entryPenalty != null)
        _RiskBadgeData(
            'Entry Penalty ${this.context.entryPenalty}', Colors.amberAccent),
      _RiskBadgeData(
        'New Buy Blocked ${this.context.hardBlockNewBuy ? 'YES' : 'NO'}',
        this.context.hardBlockNewBuy ? Colors.redAccent : Colors.greenAccent,
      ),
      if (this.context.gptBuyScore != null || this.context.gptSellScore != null)
        _RiskBadgeData(
          'GPT Score ${_scorePair(this.context.gptBuyScore, this.context.gptSellScore)}',
          Colors.lightBlueAccent,
        ),
      if (this.context.riskFlags.isNotEmpty)
        _RiskBadgeData(
            'Risk Flags ${this.context.riskFlags.length}', Colors.orangeAccent),
    ];
    if (badges.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: compact ? 5 : 8,
      runSpacing: compact ? 5 : 8,
      children: [
        for (final badge in badges)
          _RiskBadge(text: badge.text, color: badge.color),
      ],
    );
  }
}

class GptRiskContextDetails extends StatelessWidget {
  const GptRiskContextDetails({
    super.key,
    required this.context,
    this.title = 'GPT Risk Filter',
  });

  final GptRiskContext context;
  final String title;

  @override
  Widget build(BuildContext context) {
    if (!this.context.hasDetails) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title, style: const TextStyle(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      GptRiskContextSummaryBadges(context: this.context),
      const SizedBox(height: 8),
      _RiskRow('Market Risk', this.context.marketRiskRegime),
      _RiskRow('Event Risk', this.context.eventRiskLevel),
      _RiskRow('FX Risk', this.context.fxRiskLevel),
      _RiskRow('Macro Risk', this.context.macroRiskLevel),
      _RiskRow('Geopolitical Risk', this.context.geopoliticalRiskLevel),
      _RiskRow('Energy Risk', this.context.energyRiskLevel),
      _RiskRow('Entry Penalty', this.context.entryPenalty?.toString()),
      _RiskRow('New Buy Blocked', this.context.hardBlockNewBuy ? 'YES' : 'NO'),
      _RiskRow(
          'Sell/Exit Allowed', this.context.allowSellOrExit ? 'YES' : 'NO'),
      _RiskRow('GPT Buy/Sell',
          _scorePair(this.context.gptBuyScore, this.context.gptSellScore)),
      if (this.context.reason?.isNotEmpty == true)
        _RiskRow('Reason', this.context.reason),
      if (this.context.riskFlags.isNotEmpty)
        _RiskRow('Risk flags', this.context.riskFlags.join(', ')),
      if (this.context.gatingNotes.isNotEmpty)
        _RiskRow('Gating notes', this.context.gatingNotes.join(' | ')),
    ]);
  }
}

class _RiskBadgeData {
  const _RiskBadgeData(this.text, this.color);

  final String text;
  final Color color;
}

class _RiskBadge extends StatelessWidget {
  const _RiskBadge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
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

class _RiskRow extends StatelessWidget {
  const _RiskRow(this.label, this.value);

  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    final display = value == null || value!.isEmpty ? 'n/a' : value!;
    return Padding(
      padding: const EdgeInsets.only(top: 5),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 128,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
        Expanded(child: SelectableText(display)),
      ]),
    );
  }
}

Color _riskColor(String? value) {
  switch ((value ?? '').toLowerCase()) {
    case 'high':
    case 'extreme':
    case 'panic':
    case 'risk_off':
      return Colors.redAccent;
    case 'medium':
    case 'mixed':
      return Colors.amberAccent;
    case 'low':
    case 'none':
    case 'risk_on':
      return Colors.greenAccent;
    default:
      return Colors.lightBlueAccent;
  }
}

String _scorePair(double? buy, double? sell) {
  if (buy == null && sell == null) return 'n/a';
  return '${_score(buy)}/${_score(sell)}';
}

String _score(double? value) {
  if (value == null) return 'n/a';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(1);
}
