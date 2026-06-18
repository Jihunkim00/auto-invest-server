class AgentPlanRunResult {
  const AgentPlanRunResult({
    required this.status,
    required this.planId,
    required this.planRunId,
    required this.commandType,
    required this.result,
    required this.safety,
    this.errorMessage,
  });

  final String status;
  final int planId;
  final int planRunId;
  final String commandType;
  final Map<String, dynamic> result;
  final Map<String, dynamic> safety;
  final String? errorMessage;

  bool get isBlocked => status == 'blocked';
  bool get isCompleted => status == 'executed_safe_action';

  factory AgentPlanRunResult.fromJson(Map<String, dynamic> json) {
    return AgentPlanRunResult(
      status: _readString(json['status'], ''),
      planId: _readInt(json['plan_id'], 0),
      planRunId: _readInt(json['plan_run_id'], 0),
      commandType: _readString(json['command_type'], ''),
      result: _readMap(json['result']),
      safety: _readMap(json['safety']),
      errorMessage: _readNullableString(json['error_message']),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}
