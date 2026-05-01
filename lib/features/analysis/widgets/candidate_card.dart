import 'package:flutter/material.dart';

import '../../../models/candidate.dart';

class CandidateCard extends StatelessWidget {
  const CandidateCard({
    super.key,
    required this.index,
    required this.candidate,
    this.onUseInOrderTicket,
    this.useInOrderTicketLabel = 'Use in Order Ticket',
  });

  final int index;
  final Candidate candidate;
  final VoidCallback? onUseInOrderTicket;
  final String useInOrderTicketLabel;

  @override
  Widget build(BuildContext context) {
    final readinessText =
        candidate.entryReady ? 'Entry-ready' : 'Not entry-ready';
    final title = [
      candidate.symbol,
      if (candidate.name.isNotEmpty) candidate.name,
      if (candidate.market.isNotEmpty) candidate.market,
    ].join(' - ');
    final detail = [
      candidate.actionHint,
      readinessText,
      'action=${candidate.action}',
      if (candidate.blockReason != null) candidate.blockReason!,
    ].join(' | ');
    final scoreText =
        candidate.score == null ? 'Not calculated' : candidate.score.toString();
    final isPriceOnly = candidate.indicatorStatus == 'price_only' ||
        candidate.indicatorStatus == 'insufficient_data';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Row(children: [
        CircleAvatar(
            radius: 14,
            backgroundColor: Colors.white12,
            child: Text('${index + 1}')),
        const SizedBox(width: 12),
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          if (candidate.currentPrice != null) ...[
            const SizedBox(height: 2),
            Text(_formatMoney(candidate.currentPrice!, candidate.currency),
                style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ],
          if (candidate.note.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(candidate.note,
                style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ],
          if (candidate.indicatorStatus.isNotEmpty ||
              candidate.warnings.isNotEmpty) ...[
            const SizedBox(height: 6),
            Wrap(spacing: 6, runSpacing: 6, children: [
              if (candidate.indicatorStatus.isNotEmpty)
                _Badge(
                    text: _indicatorStatusLabel(candidate.indicatorStatus),
                    color: _indicatorStatusColor(candidate.indicatorStatus)),
              if (candidate.warnings.contains('preview_only') ||
                  candidate.riskFlags.contains('preview_only'))
                const _Badge(
                    text: 'PREVIEW ONLY', color: Colors.lightBlueAccent),
              if (candidate.warnings.contains('kr_trading_disabled') ||
                  candidate.riskFlags.contains('kr_trading_disabled'))
                const _Badge(
                    text: 'TRADING DISABLED', color: Colors.amberAccent),
            ]),
          ],
          const SizedBox(height: 4),
          Text(detail,
              style: TextStyle(
                  color: candidate.entryReady
                      ? Colors.greenAccent
                      : Colors.orangeAccent,
                  fontSize: 12,
                  fontWeight: FontWeight.w600)),
          if (candidate.hasScoreBreakdown || isPriceOnly) ...[
            const SizedBox(height: 10),
            const _SubsectionTitle(text: 'Score Breakdown'),
            if (candidate.hasScoreBreakdown)
              Wrap(spacing: 14, runSpacing: 8, children: [
                if (candidate.quantBuyScore != null)
                  _DataPair(
                      label: 'Quant Buy',
                      value: _score(candidate.quantBuyScore)),
                if (candidate.quantSellScore != null)
                  _DataPair(
                      label: 'Quant Sell',
                      value: _score(candidate.quantSellScore)),
                if (candidate.aiBuyScore != null)
                  _DataPair(
                      label: 'AI Buy', value: _score(candidate.aiBuyScore)),
                if (candidate.aiSellScore != null)
                  _DataPair(
                      label: 'AI Sell', value: _score(candidate.aiSellScore)),
                if (candidate.finalBuyScore != null)
                  _DataPair(
                      label: 'Final Buy',
                      value: _score(candidate.finalBuyScore)),
                if (candidate.finalSellScore != null)
                  _DataPair(
                      label: 'Final Sell',
                      value: _score(candidate.finalSellScore)),
                if (candidate.confidence != null)
                  _DataPair(
                      label: 'Confidence', value: _score(candidate.confidence)),
              ])
            else
              const Text(
                'Technical score not calculated. Reason: insufficient indicator data.',
                style: TextStyle(color: Colors.white60, fontSize: 12),
              ),
          ],
          if (candidate.indicatorPayload.isNotEmpty) ...[
            const SizedBox(height: 10),
            const _SubsectionTitle(text: 'Quant Indicators'),
            if (candidate.hasIndicatorValues)
              Wrap(spacing: 14, runSpacing: 8, children: [
                for (final entry in candidate.indicatorPayload.entries)
                  if (entry.value != null)
                    _DataPair(label: entry.key, value: entry.value.toString()),
              ])
            else
              const Text('KIS OHLCV indicators not available yet',
                  style: TextStyle(color: Colors.white60, fontSize: 12)),
          ],
          if (candidate.reason.isNotEmpty ||
              candidate.gptReason.isNotEmpty) ...[
            const SizedBox(height: 10),
            const _SubsectionTitle(text: 'GPT advisory context'),
            const Text('Quant-first \u00B7 GPT advisory only',
                style: TextStyle(color: Colors.white54, fontSize: 12)),
            const SizedBox(height: 4),
            if (candidate.reason.isNotEmpty)
              Text(candidate.reason,
                  style: const TextStyle(color: Colors.white70, fontSize: 12)),
            if (candidate.gptReason.isNotEmpty)
              Text(candidate.gptReason,
                  style: const TextStyle(color: Colors.white60, fontSize: 12)),
          ],
          if (candidate.hasRiskContext) ...[
            const SizedBox(height: 10),
            const _SubsectionTitle(text: 'Risk / Gating'),
            Wrap(spacing: 14, runSpacing: 8, children: [
              const _DataPair(label: 'Schema', value: 'Shared risk schema'),
              if (candidate.tradeAllowed != null)
                _DataPair(
                    label: 'Trade Allowed',
                    value: candidate.tradeAllowed! ? 'YES' : 'NO'),
              if (candidate.approvedByRisk != null)
                _DataPair(
                    label: 'Approved By Risk',
                    value: candidate.approvedByRisk! ? 'YES' : 'NO'),
            ]),
            if (candidate.riskFlags.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('Risk flags: ${candidate.riskFlags.join(', ')}',
                  style: const TextStyle(color: Colors.white60, fontSize: 12)),
            ],
            if (candidate.gatingNotes.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('Gating notes: ${candidate.gatingNotes.join(', ')}',
                  style: const TextStyle(color: Colors.white60, fontSize: 12)),
            ],
            if (candidate.blockReasons.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text('Block reasons: ${candidate.blockReasons.join(', ')}',
                style: const TextStyle(color: Colors.white60, fontSize: 12)),
            ],
          ],
          if (onUseInOrderTicket != null) ...[
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                onPressed: onUseInOrderTicket,
                icon: const Icon(Icons.input, size: 18),
                label: Text(useInOrderTicketLabel),
              ),
            ),
          ],
        ])),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 92),
          child: Text(scoreText,
              textAlign: TextAlign.end,
              style: TextStyle(
                  color:
                      candidate.score == null ? Colors.white60 : Colors.white,
                  fontWeight: FontWeight.bold)),
        ),
      ]),
    );
  }
}

class _SubsectionTitle extends StatelessWidget {
  const _SubsectionTitle({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(text.toUpperCase(),
          style: const TextStyle(
              color: Colors.white54,
              fontSize: 10,
              fontWeight: FontWeight.w800)),
    );
  }
}

class _DataPair extends StatelessWidget {
  const _DataPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 84, maxWidth: 150),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.toUpperCase(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white54,
                fontSize: 10,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text(value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text, required this.color});

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
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}

String _score(double? value) {
  if (value == null) return 'Not calculated';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}

String _indicatorStatusLabel(String value) {
  switch (value) {
    case 'ok':
      return 'OK';
    case 'partial':
      return 'PARTIAL';
    case 'price_only':
      return 'PRICE ONLY';
    default:
      return 'INSUFFICIENT DATA';
  }
}

Color _indicatorStatusColor(String value) {
  switch (value) {
    case 'ok':
      return Colors.greenAccent;
    case 'partial':
      return Colors.lightGreenAccent;
    case 'price_only':
      return Colors.lightBlueAccent;
    default:
      return Colors.orangeAccent;
  }
}

String _formatMoney(double value, String currency) {
  final normalizedCurrency = currency.isEmpty ? 'USD' : currency;
  final decimals = normalizedCurrency == 'KRW' ? 0 : 2;
  final amount = decimals == 0
      ? _groupedNumber(value.round())
      : value.toStringAsFixed(decimals);
  return '$normalizedCurrency $amount';
}

String _groupedNumber(int value) {
  final sign = value < 0 ? '-' : '';
  final text = value.abs().toString();
  final buffer = StringBuffer();
  for (var i = 0; i < text.length; i += 1) {
    final remaining = text.length - i;
    buffer.write(text[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return '$sign$buffer';
}
