class UserBrokerCredential {
  const UserBrokerCredential({
    required this.provider,
    required this.configured,
    this.environment,
    this.appKeyMasked,
    this.htsIdMasked,
    this.accountNoMasked,
    this.apiKeyMasked,
    this.lastValidationStatus,
    this.lastValidatedAt,
    this.lastValidationError,
    this.secretConfigured = false,
    this.appSecretConfigured = false,
    this.secretKeyConfigured = false,
  });

  final String provider;
  final bool configured;
  final String? environment;
  final String? appKeyMasked;
  final String? htsIdMasked;
  final String? accountNoMasked;
  final String? apiKeyMasked;
  final String? lastValidationStatus;
  final String? lastValidatedAt;
  final String? lastValidationError;
  final bool secretConfigured;
  final bool appSecretConfigured;
  final bool secretKeyConfigured;

  bool get validated => lastValidationStatus == 'success';

  factory UserBrokerCredential.fromJson(Map<String, dynamic> json) {
    return UserBrokerCredential(
      provider: json['provider']?.toString() ?? '',
      configured: json['configured'] == true,
      environment: _nullable(json['environment']),
      appKeyMasked: _nullable(json['app_key_masked']),
      htsIdMasked: _nullable(json['hts_id_masked']),
      accountNoMasked: _nullable(json['account_no_masked']),
      apiKeyMasked: _nullable(json['api_key_masked']),
      lastValidationStatus: _nullable(json['last_validation_status']),
      lastValidatedAt: _nullable(json['last_validated_at']),
      lastValidationError: _nullable(json['last_validation_error']),
      secretConfigured: json['secret_configured'] == true,
      appSecretConfigured: json['app_secret_configured'] == true,
      secretKeyConfigured: json['secret_key_configured'] == true,
    );
  }

  UserBrokerCredential withValidation({
    required String? status,
    required String? error,
  }) {
    return UserBrokerCredential(
      provider: provider,
      configured: configured,
      environment: environment,
      appKeyMasked: appKeyMasked,
      htsIdMasked: htsIdMasked,
      accountNoMasked: accountNoMasked,
      apiKeyMasked: apiKeyMasked,
      lastValidationStatus: status,
      lastValidatedAt: lastValidatedAt,
      lastValidationError: error,
      secretConfigured: secretConfigured,
      appSecretConfigured: appSecretConfigured,
      secretKeyConfigured: secretKeyConfigured,
    );
  }

  static String? _nullable(Object? value) {
    final text = value?.toString().trim();
    return text == null || text.isEmpty ? null : text;
  }
}
