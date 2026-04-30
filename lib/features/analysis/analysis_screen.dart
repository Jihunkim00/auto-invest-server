import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import 'widgets/analysis_metrics_section.dart';
import 'widgets/candidate_card.dart';
import 'widgets/final_candidate_section.dart';

class AnalysisScreen extends StatelessWidget {
  const AnalysisScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final r = controller.runResult;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text('Analysis', style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
              const SizedBox(height: 12),
              AnalysisMetricsSection(controller: controller),
              const SizedBox(height: 12),
              FinalCandidateSection(controller: controller),
              const SizedBox(height: 12),
              SectionCard(
                child: ExpansionTile(
                  title: const Text('Top Quant Candidates'),
                  children: [for (var i = 0; i < r.topQuantCandidates.length; i++) CandidateCard(index: i, candidate: r.topQuantCandidates[i])],
                ),
              ),
              const SizedBox(height: 12),
              SectionCard(
                child: ExpansionTile(
                  title: const Text('Researched Candidates'),
                  children: [for (var i = 0; i < r.researchedCandidates.length; i++) CandidateCard(index: i, candidate: r.researchedCandidates[i])],
                ),
              ),
              const SizedBox(height: 12),
              SectionCard(
                child: ExpansionTile(
                  title: const Text('Final Ranked Candidates'),
                  initiallyExpanded: true,
                  children: [for (var i = 0; i < r.finalRankedCandidates.length; i++) CandidateCard(index: i, candidate: r.finalRankedCandidates[i])],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
