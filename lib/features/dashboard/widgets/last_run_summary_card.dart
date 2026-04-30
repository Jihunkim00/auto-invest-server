import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class LastRunSummaryCard extends StatelessWidget {
  const LastRunSummaryCard({super.key, required this.controller});

  final DashboardController controller;

  Widget _item(String label, String value, {Color? color}) => Expanded(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label.toUpperCase(),
              style: const TextStyle(
                  color: Colors.white60,
                  fontSize: 10,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text(value,
              style: TextStyle(
                  color: color ?? Colors.white, fontWeight: FontWeight.w600)),
        ]),
      );

  @override
  Widget build(BuildContext context) {
    if (!controller.hasLatestRunResult && !controller.showingOfflineFallback) {
      return const SectionCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Last Run Summary',
              style: TextStyle(
                  fontSize: 14,
                  color: Colors.white70,
                  fontWeight: FontWeight.w700)),
          SizedBox(height: 12),
          Text('No watchlist run yet',
              style:
                  TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
        ]),
      );
    }

    final r = controller.runResult;
    final triggerText =
        r.shouldTrade ? 'Trade trigger ready' : 'No trade trigger';
    final orderText = r.orderId == null ? 'No order created' : r.orderId!;
    final resultText = r.result.isEmpty ? 'No run yet' : r.result;
    final triggerSourceText =
        r.triggerSource.isEmpty ? 'No run yet' : r.triggerSource;
    final finalBestCandidate =
        r.finalBestCandidate.isEmpty ? 'None' : r.finalBestCandidate;
    final actionText = r.action.isEmpty ? 'HOLD' : r.action.toUpperCase();
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Last Run Summary',
            style: TextStyle(
                fontSize: 14,
                color: Colors.white70,
                fontWeight: FontWeight.w700)),
        if (controller.showingOfflineFallback) ...[
          const SizedBox(height: 8),
          const Text('Offline sample data',
              style: TextStyle(
                  color: Colors.orangeAccent, fontWeight: FontWeight.w600)),
        ],
        const SizedBox(height: 12),
        Wrap(
          runSpacing: 10,
          children: [
            Row(children: [
              _item('Result', resultText),
              _item('Trigger Source', triggerSourceText)
            ]),
            Row(children: [
              _item('Final Best Candidate', finalBestCandidate),
              _item('Best Score', '${r.bestScore}')
            ]),
            Row(children: [
              _item('Entry Ready',
                  r.finalEntryReady ? 'Entry-ready' : 'Not entry-ready',
                  color: r.finalEntryReady
                      ? Colors.greenAccent
                      : Colors.orangeAccent),
              _item('Action Hint', r.finalActionHint)
            ]),
            Row(children: [
              _item('Trigger', triggerText,
                  color:
                      r.shouldTrade ? Colors.greenAccent : Colors.orangeAccent),
              _item('Order ID', orderText)
            ]),
            Row(children: [
              _item('Trigger Block Reason', r.triggerBlockReason,
                  color: Colors.orangeAccent),
              _item('Action', actionText)
            ]),
          ],
        )
      ]),
    );
  }
}
