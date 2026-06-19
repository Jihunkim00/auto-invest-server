class AgentCommandParseResult {
  const AgentCommandParseResult({
    required this.status,
    required this.parserStatus,
    required this.command,
    required this.safety,
    this.commandLogId,
    this.modelName,
    this.errorMessage,
  });

  final String status;
  final String parserStatus;
  final AutoInvestCommand command;
  final Map<String, dynamic> safety;
  final int? commandLogId;
  final String? modelName;
  final String? errorMessage;

  bool get fallbackUsed => parserStatus.toLowerCase().contains('fallback');

  factory AgentCommandParseResult.fromJson(Map<String, dynamic> json) {
    final commandJson = json['command'];
    return AgentCommandParseResult(
      status: _readString(json['status'], ''),
      parserStatus: _readString(json['parser_status'], 'fallback'),
      command: commandJson is Map
          ? AutoInvestCommand.fromJson(Map<String, dynamic>.from(commandJson))
          : AutoInvestCommand.empty(),
      safety: _readMap(json['safety']),
      commandLogId: _readNullableInt(json['command_log_id']),
      modelName: _readNullableString(json['model_name']),
      errorMessage: _readNullableString(json['error_message']),
    );
  }
}

class AutoInvestCommand {
  const AutoInvestCommand({
    required this.schemaVersion,
    required this.commandType,
    required this.domain,
    required this.intent,
    required this.market,
    required this.provider,
    required this.side,
    required this.riskLevel,
    required this.requiresAuth,
    required this.requiresRiskApproval,
    required this.needsClarification,
    required this.userVisibleSummary,
    required this.parserConfidence,
    required this.executionPolicy,
    required this.safety,
    required this.raw,
    this.symbol,
    this.quantity,
    this.budget,
    this.schedule,
    this.clarificationQuestion,
  });

  final String schemaVersion;
  final String commandType;
  final String domain;
  final String intent;
  final String market;
  final String provider;
  final String? symbol;
  final String side;
  final double? quantity;
  final Map<String, dynamic>? budget;
  final Map<String, dynamic>? schedule;
  final String riskLevel;
  final bool requiresAuth;
  final bool requiresRiskApproval;
  final bool needsClarification;
  final String? clarificationQuestion;
  final String userVisibleSummary;
  final double parserConfidence;
  final Map<String, dynamic> executionPolicy;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> raw;

  factory AutoInvestCommand.empty() {
    return const AutoInvestCommand(
      schemaVersion: '',
      commandType: 'UNKNOWN',
      domain: 'unknown',
      intent: 'unknown',
      market: 'UNKNOWN',
      provider: 'unknown',
      side: 'none',
      riskLevel: 'unknown',
      requiresAuth: false,
      requiresRiskApproval: false,
      needsClarification: false,
      userVisibleSummary: 'Command parsed for review. No action was executed.',
      parserConfidence: 0,
      executionPolicy: {},
      safety: {},
      raw: {},
    );
  }

  factory AutoInvestCommand.fromJson(Map<String, dynamic> json) {
    final budget = json['budget'];
    final schedule = json['schedule'];
    return AutoInvestCommand(
      schemaVersion: _readString(json['schema_version'], ''),
      commandType: _readString(json['command_type'], 'UNKNOWN'),
      domain: _readString(json['domain'], 'unknown'),
      intent: _readString(json['intent'], 'unknown'),
      market: _readString(json['market'], 'UNKNOWN'),
      provider: _readString(json['provider'], 'unknown'),
      symbol: _readNullableString(json['symbol']),
      side: _readString(json['side'], 'none'),
      quantity: _readNullableDouble(json['quantity']),
      budget: budget is Map ? Map<String, dynamic>.from(budget) : null,
      schedule: schedule is Map ? Map<String, dynamic>.from(schedule) : null,
      riskLevel: _readString(json['risk_level'], 'unknown'),
      requiresAuth: json['requires_auth'] == true,
      requiresRiskApproval: json['requires_risk_approval'] == true,
      needsClarification: json['needs_clarification'] == true,
      clarificationQuestion:
          _readNullableString(json['clarification_question']),
      userVisibleSummary: _readString(
        json['user_visible_summary'],
        'Command parsed for review. No action was executed.',
      ),
      parserConfidence: _readDouble(json['parser_confidence'], 0),
      executionPolicy: _readMap(json['execution_policy']),
      safety: _readMap(json['safety']),
      raw: Map<String, dynamic>.from(json),
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

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

double _readDouble(Object? value, double fallback) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? fallback;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}
