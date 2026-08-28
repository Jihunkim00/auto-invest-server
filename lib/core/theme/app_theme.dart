import 'package:flutter/material.dart';

class AppTheme {
  // AUTO INVEST dark-fintech tokens. Keep surfaces quiet so safety state and
  // account values remain the strongest visual signals.
  static const canvas = Color(0xFF090B0D);
  static const surface = Color(0xFF111518);
  static const surfaceElevated = Color(0xFF171C20);
  static const hairline = Color(0x1FFFFFFF);
  static const primaryAccent = Color(0xFF9AA8FF);
  static const positive = Color(0xFF48D597);
  static const warning = Color(0xFFFFB454);
  static const danger = Color(0xFFFF6B78);

  // Kept as aliases for older widgets that reference the original names.
  static const background = canvas;
  static const panel = surface;
  static const panelInner = surfaceElevated;

  static const cardRadius = 20.0;
  static const inputRadius = 12.0;
  static const inputMinHeight = 52.0;
  static const pagePadding = 16.0;

  static ThemeData get darkTheme {
    final scheme = ColorScheme.dark(
      surface: canvas,
      onSurface: Colors.white,
      primary: primaryAccent,
      onPrimary: const Color(0xFF0B0D10),
      secondary: const Color(0xFFB8C0CA),
      onSecondary: const Color(0xFF0B0D10),
      error: danger,
      onError: Colors.white,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: scheme,
      scaffoldBackgroundColor: canvas,
      cardColor: surface,
      fontFamilyFallback: const ['Noto Sans KR', 'Malgun Gothic', 'Arial'],
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          fontSize: 28,
          height: 1.25,
          fontWeight: FontWeight.w700,
        ),
        titleLarge: TextStyle(
          fontSize: 22,
          height: 1.3,
          fontWeight: FontWeight.w800,
        ),
        titleMedium: TextStyle(
          fontSize: 18,
          height: 1.35,
          fontWeight: FontWeight.w700,
        ),
        bodyLarge: TextStyle(fontSize: 16, height: 1.5),
        bodyMedium: TextStyle(fontSize: 14, height: 1.5),
        labelLarge:
            TextStyle(fontSize: 14, height: 1.4, fontWeight: FontWeight.w700),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceElevated,
        constraints: const BoxConstraints(minHeight: inputMinHeight),
        contentPadding:
            const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(inputRadius),
          borderSide: const BorderSide(color: hairline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(inputRadius),
          borderSide: const BorderSide(color: hairline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(inputRadius),
          borderSide: const BorderSide(color: primaryAccent, width: 1.3),
        ),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(cardRadius),
          side: const BorderSide(color: hairline),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, 46),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
          shape: const StadiumBorder(),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 46),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          shape: const StadiumBorder(),
          side: const BorderSide(color: hairline),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: surfaceElevated,
        selectedColor: primaryAccent.withValues(alpha: 0.18),
        side: const BorderSide(color: hairline),
        shape: const StadiumBorder(),
        labelStyle: const TextStyle(fontWeight: FontWeight.w700),
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: const Color(0xFF0D1012),
        indicatorColor: primaryAccent.withValues(alpha: 0.18),
        labelTextStyle: const WidgetStatePropertyAll(
          TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}
