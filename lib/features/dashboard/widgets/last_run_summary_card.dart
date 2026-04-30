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
    final r = controller.runResult;
    final triggerText =
        r.shouldTrade ? 'Trade trigger ready' : 'No trade trigger';
    final orderText = r.orderId == null ? 'No order created' : r.orderId!;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Last Run Summary',
            style: TextStyle(
                fontSize: 14,
                color: Colors.white70,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 12),
        Wrap(
          runSpacing: 10,
          children: [
            Row(children: [
              _item('Result', r.result),
              _item('Trigger Source', r.triggerSource)
            ]),
            Row(children: [
              _item('Final Best Candidate', r.finalBestCandidate),
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
              _item(
                  'Action', r.action.isEmpty ? 'HOLD' : r.action.toUpperCase())
            ]),
          ],
        )
      ]),
    );
  }
}
