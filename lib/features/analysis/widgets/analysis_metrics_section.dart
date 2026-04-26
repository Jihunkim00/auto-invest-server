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
          Text('Configured/Analyzed: ${r.configuredSymbolCount}/${r.analyzedSymbolCount}'),
          Text('Quant/Researched: ${r.quantCandidatesCount}/${r.researchedCandidatesCount}'),
          Text('Final score gap: ${r.finalScoreGap} (min ${r.minScoreGap})'),
          Text('Min entry score: ${r.minEntryScore}'),
          Text('Should trade: ${r.shouldTrade}'),
          Text('Triggered symbol: ${r.triggeredSymbol ?? 'null'}'),
          Text('Trigger block reason: ${r.triggerBlockReason}', style: const TextStyle(color: Colors.orangeAccent)),
          Text('Trade result: ${r.action} / order_id: ${r.orderId}'),
        ],
      ),
    );
  }
}
