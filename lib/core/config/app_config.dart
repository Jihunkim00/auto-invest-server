import 'package:flutter/foundation.dart';

class AppConfig {
  static String get baseUrl {
    if (kIsWeb) return 'http://127.0.0.1:8000';
    return defaultTargetPlatform == TargetPlatform.android ? 'http://10.0.2.2:8000' : 'http://127.0.0.1:8000';
  }
}
