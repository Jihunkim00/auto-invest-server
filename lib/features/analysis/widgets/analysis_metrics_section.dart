import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class AnalysisMetricsSection extends StatelessWidget {
  const AnalysisMetricsSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final r = controller.runResult;
    return SectionCard(
      child: Wrap(
        runSpacing: 8,
        children: [
          Text(
              'Configured/Analyzed: ${r.configuredSymbolCount}/${r.analyzedSymbolCount}'),
          Text(
              'Quant/Researched: ${r.quantCandidatesCount}/${r.researchedCandidatesCount}'),
          Text(
              'Final score gap: ${_valueOrNotCalculated(r.finalScoreGap)} (min ${_valueOrNotCalculated(r.minScoreGap)})'),
          Text('Min entry score: ${_valueOrNotCalculated(r.minEntryScore)}'),
          Text(
              'Entry ready: ${r.finalEntryReady ? 'Entry-ready' : 'Not entry-ready'}'),
          Text('Action hint: ${r.finalActionHint}'),
          Text(
              'Should trade: ${r.shouldTrade ? 'Trade trigger ready' : 'No trade trigger'}'),
          Text('Triggered symbol: ${r.triggeredSymbol ?? 'null'}'),
          Text('Trigger block reason: ${r.triggerBlockReason}',
              style: const TextStyle(color: Colors.orangeAccent)),
          Text(
              'Trade result: ${r.action.isEmpty ? 'hold' : r.action} / ${r.orderId == null ? 'No order created' : 'order_id: ${r.orderId}'}'),
        ],
      ),
    );
  }
}

String _valueOrNotCalculated(num? value) {
  if (value == null) return 'Not calculated';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}
