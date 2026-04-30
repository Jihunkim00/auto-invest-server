class Candidate {
  const Candidate({
    required this.symbol,
    required this.score,
    required this.note,
    required this.entryReady,
    required this.actionHint,
    required this.blockReason,
  });

  final String symbol;
  final int score;
  final String note;
  final bool entryReady;
  final String actionHint;
  final String? blockReason;

  factory Candidate.fromJson(Map<String, dynamic> json,
      {String scoreKey = 'score', String noteKey = 'note'}) {
    final rawScore = json[scoreKey];
    final score = rawScore is num
        ? rawScore.round()
        : int.tryParse(rawScore?.toString() ?? '') ?? 0;
    return Candidate(
      symbol: json['symbol']?.toString() ?? '',
      score: score,
      note: json[noteKey]?.toString() ?? '',
      entryReady: json['entry_ready'] == true,
      actionHint: json['action_hint']?.toString() ?? 'watch',
      blockReason: json['block_reason']?.toString(),
    );
  }
}
