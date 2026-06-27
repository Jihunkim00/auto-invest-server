enum AppLanguage {
  korean,
  english,
}

extension AppLanguageX on AppLanguage {
  String get code {
    switch (this) {
      case AppLanguage.korean:
        return 'ko';
      case AppLanguage.english:
        return 'en';
    }
  }

  String get localeCode {
    switch (this) {
      case AppLanguage.korean:
        return 'ko-KR';
      case AppLanguage.english:
        return 'en-US';
    }
  }

  String get languageCode {
    switch (this) {
      case AppLanguage.korean:
        return 'ko';
      case AppLanguage.english:
        return 'en';
    }
  }

  String get label {
    switch (this) {
      case AppLanguage.korean:
        return '한국어';
      case AppLanguage.english:
        return 'English';
    }
  }
}

AppLanguage appLanguageFromCode(Object? value) {
  final normalized = value?.toString().trim().toLowerCase();
  if (normalized == 'en' || normalized == 'en-us' || normalized == 'english') {
    return AppLanguage.english;
  }
  return AppLanguage.korean;
}
