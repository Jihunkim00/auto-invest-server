class StrategyProfile {
  const StrategyProfile({
    required this.id,
    required this.profileName,
    required this.displayName,
    required this.monthlyTargetReturnPct,
    required this.monthlyTargetMinPct,
    required this.monthlyTargetMaxPct,
    required this.monthlyMaxLossPct,
    required this.dailyMaxLossPct,
    required this.maxOrderNotionalPct,
    required this.maxOrderNotionalKrw,
    required this.maxTradesPerDay,
    required this.maxPositions,
    required this.buyScoreThreshold,
    required this.sellScoreThreshold,
    required this.stopLossPct,
    required this.takeProfitPct,
    required this.maxHoldingDays,
    required this.stopAfterMonthlyTarget,
    required this.reduceSizeAfterLoss,
    required this.consecutiveLossReduceThreshold,
    required this.isActive,
    required this.isBuiltin,
    this.description,
    this.raw = const {},
  });

  final int id;
  final String profileName;
  final String displayName;
  final String? description;
  final double monthlyTargetReturnPct;
  final double monthlyTargetMinPct;
  final double monthlyTargetMaxPct;
  final double monthlyMaxLossPct;
  final double dailyMaxLossPct;
  final double maxOrderNotionalPct;
  final double maxOrderNotionalKrw;
  final int maxTradesPerDay;
  final int maxPositions;
  final double buyScoreThreshold;
  final double sellScoreThreshold;
  final double stopLossPct;
  final double takeProfitPct;
  final int maxHoldingDays;
  final bool stopAfterMonthlyTarget;
  final bool reduceSizeAfterLoss;
  final int consecutiveLossReduceThreshold;
  final bool isActive;
  final bool isBuiltin;
  final Map<String, dynamic> raw;

  bool get isAggressive => profileName == 'aggressive';

  factory StrategyProfile.fromJson(Map<String, dynamic> json) {
    return StrategyProfile(
      id: _readInt(json['id']),
      profileName: _readString(json['profile_name'], ''),
      displayName: _readString(json['display_name'], ''),
      description: _readNullableString(json['description']),
      monthlyTargetReturnPct: _readDouble(json['monthly_target_return_pct']),
      monthlyTargetMinPct: _readDouble(json['monthly_target_min_pct']),
      monthlyTargetMaxPct: _readDouble(json['monthly_target_max_pct']),
      monthlyMaxLossPct: _readDouble(json['monthly_max_loss_pct']),
      dailyMaxLossPct: _readDouble(json['daily_max_loss_pct']),
      maxOrderNotionalPct: _readDouble(json['max_order_notional_pct']),
      maxOrderNotionalKrw: _readDouble(json['max_order_notional_krw']),
      maxTradesPerDay: _readInt(json['max_trades_per_day']),
      maxPositions: _readInt(json['max_positions']),
      buyScoreThreshold: _readDouble(json['buy_score_threshold']),
      sellScoreThreshold: _readDouble(json['sell_score_threshold']),
      stopLossPct: _readDouble(json['stop_loss_pct']),
      takeProfitPct: _readDouble(json['take_profit_pct']),
      maxHoldingDays: _readInt(json['max_holding_days']),
      stopAfterMonthlyTarget: json['stop_after_monthly_target'] == true,
      reduceSizeAfterLoss: json['reduce_size_after_loss'] != false,
      consecutiveLossReduceThreshold:
          _readInt(json['consecutive_loss_reduce_threshold']),
      isActive: json['is_active'] == true,
      isBuiltin: json['is_builtin'] != false,
      raw: Map<String, dynamic>.from(json),
    );
  }

  Map<String, dynamic> toJson() => raw.isNotEmpty
      ? raw
      : {
          'id': id,
          'profile_name': profileName,
          'display_name': displayName,
          'description': description,
          'monthly_target_return_pct': monthlyTargetReturnPct,
          'monthly_target_min_pct': monthlyTargetMinPct,
          'monthly_target_max_pct': monthlyTargetMaxPct,
          'monthly_max_loss_pct': monthlyMaxLossPct,
          'daily_max_loss_pct': dailyMaxLossPct,
          'max_order_notional_pct': maxOrderNotionalPct,
          'max_order_notional_krw': maxOrderNotionalKrw,
          'max_trades_per_day': maxTradesPerDay,
          'max_positions': maxPositions,
          'buy_score_threshold': buyScoreThreshold,
          'sell_score_threshold': sellScoreThreshold,
          'stop_loss_pct': stopLossPct,
          'take_profit_pct': takeProfitPct,
          'max_holding_days': maxHoldingDays,
          'stop_after_monthly_target': stopAfterMonthlyTarget,
          'reduce_size_after_loss': reduceSizeAfterLoss,
          'consecutive_loss_reduce_threshold': consecutiveLossReduceThreshold,
          'is_active': isActive,
          'is_builtin': isBuiltin,
        };
}

class StrategyProfileList {
  const StrategyProfileList({
    required this.profiles,
    required this.activeProfile,
  });

  final List<StrategyProfile> profiles;
  final StrategyProfile activeProfile;

  factory StrategyProfileList.fromJson(Map<String, dynamic> json) {
    final items = json['profiles'] as List<dynamic>? ?? const [];
    final profiles = [
      for (final item in items)
        if (item is Map)
          StrategyProfile.fromJson(Map<String, dynamic>.from(item)),
    ];
    final activeJson = json['active_profile'];
    final active = activeJson is Map
        ? StrategyProfile.fromJson(Map<String, dynamic>.from(activeJson))
        : profiles.firstWhere(
            (item) => item.isActive,
            orElse: () => profiles.isEmpty
                ? StrategyProfile.fromJson(const {
                    'id': 0,
                    'profile_name': 'safe',
                    'display_name': '안정형',
                  })
                : profiles.first,
          );
    return StrategyProfileList(profiles: profiles, activeProfile: active);
  }
}

class StrategyProfileApplyResult {
  const StrategyProfileApplyResult({
    required this.status,
    required this.activeProfile,
    required this.safety,
    this.auditId,
  });

  final String status;
  final StrategyProfile activeProfile;
  final Map<String, dynamic> safety;
  final int? auditId;

  factory StrategyProfileApplyResult.fromJson(Map<String, dynamic> json) {
    return StrategyProfileApplyResult(
      status: _readString(json['status'], 'ok'),
      activeProfile: StrategyProfile.fromJson(
        Map<String, dynamic>.from(json['active_profile'] as Map),
      ),
      safety: _readMap(json['safety']),
      auditId: _readNullableInt(json['audit_id']),
    );
  }
}

String strategyProfileLabel(String profileName) {
  switch (profileName) {
    case 'safe':
      return '안정형';
    case 'balanced':
      return '보통형';
    case 'aggressive':
      return '고수익형';
  }
  return profileName;
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

int _readInt(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

double _readDouble(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? 0;
}
