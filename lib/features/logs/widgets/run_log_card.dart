import 'package:flutter/material.dart';

import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/status_badge.dart';
import '../../../models/trading_run.dart';

class RunLogCard extends StatelessWidget {
  const RunLogCard({super.key, required this.run});

  final TradingRun run;

  @override
  Widget build(BuildContext context) {
    final orderText = run.orderId == null ? 'No order' : run.orderId!;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Expanded(child: Text(formatTimestampWithKst(run.timestamp))),
            StatusBadge(
              text: run.result,
              active: run.result == 'executed',
              alert: run.result != 'executed',
            ),
          ]),
          const SizedBox(height: 6),
          Text(
              '${run.symbol} | ${run.triggerSource} | ${run.action.toUpperCase()}'),
          Text('reason: ${run.reason.isEmpty ? 'none' : run.reason}',
              style: const TextStyle(color: Colors.white70)),
          Text('best_score: ${run.bestScore} | order: $orderText',
              style: const TextStyle(color: Colors.white70)),
        ]),
      ),
    );
  }
}
