import 'package:flutter/material.dart';

import '../../../models/candidate.dart';

class CandidateCard extends StatelessWidget {
  const CandidateCard({super.key, required this.index, required this.candidate});

  final int index;
  final Candidate candidate;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.04),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.08)),
      ),
      child: Row(children: [
        CircleAvatar(radius: 14, backgroundColor: Colors.white12, child: Text('${index + 1}')),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(candidate.symbol, style: const TextStyle(fontWeight: FontWeight.bold)), Text(candidate.note, style: const TextStyle(color: Colors.white60, fontSize: 12))])),
        Text('${candidate.score}', style: const TextStyle(fontWeight: FontWeight.bold)),
      ]),
    );
  }
}
