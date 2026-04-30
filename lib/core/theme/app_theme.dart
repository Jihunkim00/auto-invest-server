import 'package:flutter/material.dart';

class AppTheme {
  static const background = Color(0xFF141313);
  static const panel = Color(0x99101010);
  static const panelInner = Color(0xFF201F1F);

  static ThemeData get darkTheme {
    final scheme = ColorScheme.fromSeed(
            seedColor: Colors.white, brightness: Brightness.dark)
        .copyWith(
      surface: background,
      primary: Colors.white,
      secondary: const Color(0xFFC4C7C8),
      error: const Color(0xFFEF4444),
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: background,
      cardColor: panel,
      textTheme: const TextTheme(
        headlineMedium: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
        titleMedium: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: Colors.black.withValues(alpha: 0.95),
        indicatorColor: Colors.white12,
      ),
    );
  }
}
