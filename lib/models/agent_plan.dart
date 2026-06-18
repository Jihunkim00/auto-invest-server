class AgentPlanCreateResult {
  const AgentPlanCreateResult({
    required this.status,
    required this.plan,
    required this.auth,
    required this.safety,
  });

  final String status;
  final AgentPlan plan;
  final Map<String, dynamic> auth;
  final Map<String, dynamic> safety;

  factory AgentPlanCreateResult.fromJson(Map<String, dynamic> json) {
    final planJson = json['plan'];
    return AgentPlanCreateResult(
      status: _readString(json['status'], ''),
      plan: planJson is Map
          ? AgentPlan.fromJson(Map<String, dynamic>.from(planJson))
          : AgentPlan.empty(),
      auth: _readMap(json['auth']),
      safety: _readMap(json['safety']),
    );
  }
}

class AgentPlan {
  const AgentPlan({
    required this.id,
    required this.planKey,
    required this.commandType,
    required this.domain,
    required this.intent,
    required this.market,
    required this.provider,
    required this.side,
    required this.riskLevel,
    required this.status,
    required this.planTitle,
    required this.planSummary,
    required this.userVisibleSummary,
    required this.command,
    required this.executionPolicy,
    required this.safety,
    required this.requiresAuth,
    required this.requiresRiskApproval,
    required this.requiresConfirmLive,
    required this.requiresRecentValidation,
    required this.allowLiveOrder,
    required this.allowSettingChange,
    required this.allowSchedulerChange,
    required this.raw,
    this.conversationId,
    this.commandLogId,
    this.symbol,
    this.scopeHash,
  });

  final int id;
  final String planKey;
  final String? conversationId;
  final int? commandLogId;
  final String commandType;
  final String domain;
  final String intent;
  final String market;
  final String provider;
  final String? symbol;
  final String side;
  final String riskLevel;
  final String status;
  final String planTitle;
  final String planSummary;
  final String userVisibleSummary;
  final Map<String, dynamic> command;
  final Map<String, dynamic> executionPolicy;
  final Map<String, dynamic> safety;
  final String? scopeHash;
  final bool requiresAuth;
  final bool requiresRiskApproval;
  final bool requiresConfirmLive;
  final bool requiresRecentValidation;
  final bool allowLiveOrder;
  final bool allowSettingChange;
  final bool allowSchedulerChange;
  final Map<String, dynamic> raw;

  bool get isAuthRequired =>
      requiresAuth || status == 'pending_auth' || status == 'auth_requested';

  bool get isBlocked =>
      status == 'blocked' || status == 'cancelled' || status == 'expired';

  bool get isManualTicketPlan =>
      commandType == 'PREPARE_MANUAL_BUY_TICKET' ||
      commandType == 'PREPARE_MANUAL_SELL_TICKET' ||
      riskLevel == 'prefill_only';

  bool get canPrepareManualTicket =>
      isManualTicketPlan && !isAuthRequired && !isBlocked;

  bool get canRunSafeAction {
    if (isAuthRequired || isBlocked || isManualTicketPlan) return false;
    if (allowLiveOrder || allowSettingChange || allowSchedulerChange) {
      return false;
    }
    return riskLevel == 'read_only' ||
        riskLevel == 'analysis_only' ||
        riskLevel == 'settings_safe' ||
        domain == 'analysis' ||
        domain == 'portfolio' ||
        domain == 'position' ||
        domain == 'logs' ||
        domain == 'watchlist';
  }

  Object? get notional => _budgetValue('amount');
  Object? get currency => _budgetValue('currency');
  Object? get quantity => command['quantity'];

  factory AgentPlan.empty() {
    return const AgentPlan(
      id: 0,
      planKey: '',
      commandType: 'UNKNOWN',
      domain: 'unknown',
      intent: 'unknown',
      market: 'UNKNOWN',
      provider: 'unknown',
      side: 'none',
      riskLevel: 'unknown',
      status: 'unknown',
      planTitle: 'Plan review',
      planSummary: 'No plan loaded.',
      userVisibleSummary: 'No plan loaded.',
      command: {},
      executionPolicy: {},
      safety: {},
      requiresAuth: false,
      requiresRiskApproval: false,
      requiresConfirmLive: false,
      requiresRecentValidation: false,
      allowLiveOrder: false,
      allowSettingChange: false,
      allowSchedulerChange: false,
      raw: {},
    );
  }

  factory AgentPlan.fromJson(Map<String, dynamic> json) {
    return AgentPlan(
      id: _readInt(json['id'], 0),
      planKey: _readString(json['plan_key'], ''),
      conversationId: _readNullableString(json['conversation_id']),
      commandLogId: _readNullableInt(json['command_log_id']),
      commandType: _readString(json['command_type'], 'UNKNOWN'),
      domain: _readString(json['domain'], 'unknown'),
      intent: _readString(json['intent'], 'unknown'),
      market: _readString(json['market'], 'UNKNOWN'),
      provider: _readString(json['provider'], 'unknown'),
      symbol: _readNullableString(json['symbol']),
      side: _readString(json['side'], 'none'),
      riskLevel: _readString(json['risk_level'], 'unknown'),
      status: _readString(json['status'], 'unknown'),
      planTitle: _readString(json['plan_title'], 'Plan review'),
      planSummary: _readString(json['plan_summary'], ''),
      userVisibleSummary: _readString(json['user_visible_summary'], ''),
      command: _readMap(json['command']),
      executionPolicy: _readMap(json['execution_policy']),
      safety: _readMap(json['safety']),
      scopeHash: _readNullableString(json['scope_hash']),
      requiresAuth: json['requires_auth'] == true,
      requiresRiskApproval: json['requires_risk_approval'] == true,
      requiresConfirmLive: json['requires_confirm_live'] == true,
      requiresRecentValidation: json['requires_recent_validation'] == true,
      allowLiveOrder: json['allow_live_order'] == true,
      allowSettingChange: json['allow_setting_change'] == true,
      allowSchedulerChange: json['allow_scheduler_change'] == true,
      raw: Map<String, dynamic>.from(json),
    );
  }

  Object? _budgetValue(String key) {
    final budget = command['budget'];
    if (budget is Map) return budget[key];
    return null;
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

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}
