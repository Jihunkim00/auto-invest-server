import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../dashboard/dashboard_controller.dart';

class FinalCandidateSection extends StatelessWidget {
  const FinalCandidateSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final r = controller.runResult;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Final Candidate Decision',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
        const SizedBox(height: 10),
        Text(
            'Best: ${r.finalBestCandidate.isEmpty ? 'None' : r.finalBestCandidate} (${_valueOrNotCalculated(r.bestScore)})'),
        Text(
            'Second: ${r.secondFinalCandidate.isEmpty ? 'None' : r.secondFinalCandidate}'),
        Text(
            'Tied: ${r.tiedFinalCandidates.isEmpty ? 'None' : r.tiedFinalCandidates.join(', ')}'),
        Text(
            'Near tied: ${r.nearTiedCandidates.isEmpty ? 'None' : r.nearTiedCandidates.join(', ')}'),
        Text('Tie-breaker applied: ${r.tieBreakerApplied}'),
        const SizedBox(height: 6),
        Text(r.finalCandidateSelectionReason,
            style: const TextStyle(color: Colors.white70)),
      ]),
    );
  }
}

String _valueOrNotCalculated(num? value) {
  if (value == null) return 'Not calculated';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}
