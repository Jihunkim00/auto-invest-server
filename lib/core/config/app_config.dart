import 'package:flutter/foundation.dart';

class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static bool get hasApiOverride =>
      const String.fromEnvironment('API_BASE_URL').isNotEmpty;

  static String get resolvedApiBaseUrl {
    if (hasApiOverride) return apiBaseUrl;
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      return 'http://10.0.2.2:8000';
    }
    return apiBaseUrl;
  }
}
