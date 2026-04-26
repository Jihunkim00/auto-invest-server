import 'candidate.dart';

class WatchlistRunResult {
  const WatchlistRunResult({
    required this.configuredSymbolCount,
    required this.analyzedSymbolCount,
    required this.quantCandidatesCount,
    required this.researchedCandidatesCount,
    required this.finalBestCandidate,
    required this.secondFinalCandidate,
    required this.tiedFinalCandidates,
    required this.nearTiedCandidates,
    required this.tieBreakerApplied,
    required this.finalCandidateSelectionReason,
    required this.bestScore,
    required this.finalScoreGap,
    required this.minEntryScore,
    required this.minScoreGap,
    required this.shouldTrade,
    required this.triggeredSymbol,
    required this.triggerBlockReason,
    required this.action,
    required this.orderId,
    required this.topQuantCandidates,
    required this.researchedCandidates,
    required this.finalRankedCandidates,
    required this.result,
    required this.reason,
    required this.triggerSource,
  });

  final int configuredSymbolCount;
  final int analyzedSymbolCount;
  final int quantCandidatesCount;
  final int researchedCandidatesCount;
  final String finalBestCandidate;
  final String secondFinalCandidate;
  final List<String> tiedFinalCandidates;
  final List<String> nearTiedCandidates;
  final bool tieBreakerApplied;
  final String finalCandidateSelectionReason;
  final int bestScore;
  final int finalScoreGap;
  final int minEntryScore;
  final int minScoreGap;
  final bool shouldTrade;
  final String? triggeredSymbol;
  final String triggerBlockReason;
  final String action;
  final String? orderId;
  final List<Candidate> topQuantCandidates;
  final List<Candidate> researchedCandidates;
  final List<Candidate> finalRankedCandidates;
  final String result;
  final String reason;
  final String triggerSource;
}
