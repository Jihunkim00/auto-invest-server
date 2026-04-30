import 'package:flutter/material.dart';

import '../../../models/candidate.dart';

class CandidateCard extends StatelessWidget {
  const CandidateCard(
      {super.key, required this.index, required this.candidate});

  final int index;
  final Candidate candidate;

  @override
  Widget build(BuildContext context) {
    final readinessText =
        candidate.entryReady ? 'Entry-ready' : 'Not entry-ready';
    final detail = [
      candidate.actionHint,
      readinessText,
      if (candidate.blockReason != null) candidate.blockReason!,
    ].join(' | ');

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
          Text(candidate.symbol,
              style: const TextStyle(fontWeight: FontWeight.bold)),
          Text(candidate.note,
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
          Text(detail,
              style: TextStyle(
                  color: candidate.entryReady
                      ? Colors.greenAccent
                      : Colors.orangeAccent,
                  fontSize: 12,
                  fontWeight: FontWeight.w600))
        ])),
        Text('${candidate.score}',
            style: const TextStyle(fontWeight: FontWeight.bold)),
      ]),
    );
  }
}
