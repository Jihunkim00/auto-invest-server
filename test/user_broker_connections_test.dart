import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/user/user_settings_screen.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';
import 'package:auto_invest_dashboard/models/user_watchlist_item.dart';

void main() {
  testWidgets('unconfigured brokers disable Validate', (tester) async {
    await _pumpScreen(tester, _BrokerSettingsApi());

    for (final provider in const ['kis', 'alpaca']) {
      expect(_validateButton(tester, provider).onPressed, isNull);
    }
  });

  testWidgets('configured brokers enable Validate with empty fields',
      (tester) async {
    await _pumpScreen(
      tester,
      _BrokerSettingsApi(configuredProviders: const {'kis', 'alpaca'}),
    );

    for (final provider in const ['kis', 'alpaca']) {
      expect(_validateButton(tester, provider).onPressed, isNotNull);
    }
    _expectFieldsEmpty(tester, const [
      'user-broker-kis-app-key',
      'user-broker-kis-app-secret',
      'user-broker-kis-hts-id',
      'user-broker-kis-account-no',
      'user-broker-kis-product-code',
      'user-broker-alpaca-api-key',
      'user-broker-alpaca-secret-key',
    ]);
  });

  testWidgets('Validate calls each stored-credential endpoint once',
      (tester) async {
    final api = _BrokerSettingsApi(
      configuredProviders: const {'kis', 'alpaca'},
    );
    await _pumpScreen(tester, api);

    for (final provider in const ['kis', 'alpaca']) {
      await tester.ensureVisible(
        find.byKey(ValueKey('user-broker-$provider-validate')),
      );
      await tester.tap(find.byKey(ValueKey('user-broker-$provider-validate')));
      await tester.pumpAndSettle();
    }

    expect(api.validationCalls, 2);
    expect(api.validationRequests, ['kis', 'alpaca']);
  });

  testWidgets('successful save clears inputs and keeps Validate enabled',
      (tester) async {
    final api = _BrokerSettingsApi();
    await _pumpScreen(tester, api);

    await _fillKis(tester);
    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-save')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-save')));
    await tester.pumpAndSettle();
    _expectFieldsEmpty(tester, const [
      'user-broker-kis-app-key',
      'user-broker-kis-app-secret',
      'user-broker-kis-hts-id',
      'user-broker-kis-account-no',
      'user-broker-kis-product-code',
    ]);
    expect(_validateButton(tester, 'kis').onPressed, isNotNull);

    await _fillAlpaca(tester);
    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-alpaca-save')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-alpaca-save')));
    await tester.pumpAndSettle();
    _expectFieldsEmpty(tester, const [
      'user-broker-alpaca-api-key',
      'user-broker-alpaca-secret-key',
    ]);
    expect(_validateButton(tester, 'alpaca').onPressed, isNotNull);
  });

  testWidgets('successful remove disables Validate', (tester) async {
    final api = _BrokerSettingsApi(
      configuredProviders: const {'kis', 'alpaca'},
    );
    await _pumpScreen(tester, api);

    for (final provider in const ['kis', 'alpaca']) {
      await tester.ensureVisible(
        find.byKey(ValueKey('user-broker-$provider-remove')),
      );
      await tester.tap(find.byKey(ValueKey('user-broker-$provider-remove')));
      await tester.pumpAndSettle();
      expect(_validateButton(tester, provider).onPressed, isNull);
    }

    expect(api.removeCalls, 2);
  });

  test('validate posts no plaintext credentials', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode({
            'provider': request.url.pathSegments[3],
            'valid': true,
            'status': 'success',
            'message': null,
          }),
          200,
        );
      }),
    );

    await api.validateUserBroker('kis');
    await api.validateUserBroker('alpaca');

    expect(
      requests.map((request) => request.url.path).toList(),
      ['/users/me/brokers/kis/validate', '/users/me/brokers/alpaca/validate'],
    );
    for (final request in requests) {
      expect(request.method, 'POST');
      expect(request.body, isEmpty);
      expect(request.body, isNot(contains('app_key')));
      expect(request.body, isNot(contains('api_key')));
      expect(request.body, isNot(contains('app_secret')));
      expect(request.body, isNot(contains('secret_key')));
    }
  });

  testWidgets(
      'regular user can manage broker credentials without refilling secrets',
      (tester) async {
    final api = _BrokerSettingsApi();
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() async {
      await tester.binding.setSurfaceSize(null);
    });

    await tester.pumpWidget(
      MaterialApp(
        home: UserSettingsScreen(
          apiClient: api,
          user: const AuthUser(
            username: 'regular-user',
            role: 'user',
            enabled: true,
            setupCompleted: true,
          ),
          onLogout: () async {},
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('user-broker-connections-card')),
        findsOneWidget);
    expect(find.text('증권사 연결'), findsOneWidget);
    expect(find.text('한국투자증권'), findsOneWidget);
    expect(find.text('거래 환경'), findsNWidgets(2));
    expect(find.text('앱 키'), findsOneWidget);
    expect(find.text('앱 시크릿'), findsOneWidget);
    expect(find.text('HTS ID'), findsOneWidget);
    expect(find.text('계좌번호'), findsOneWidget);
    expect(find.text('API 키'), findsOneWidget);
    expect(find.text('시크릿 키'), findsOneWidget);
    expect(find.text('저장'), findsNWidgets(2));
    expect(find.text('연결 확인'), findsNWidgets(2));
    expect(find.text('모의투자 환경입니다.'), findsNWidgets(2));
    expect(find.text('한국투자증권 Open API에서 발급받은 정보를 입력하세요.'), findsOneWidget);
    expect(find.text('Alpaca에서 발급받은 API 정보를 입력하세요.'), findsOneWidget);
    expect(find.text('미설정'), findsNWidgets(2));

    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-app-key')),
      'user-app-key',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-app-secret')),
      'user-app-secret',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-hts-id')),
      'user-hts-id',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-account-no')),
      '12345678',
    );
    await tester.enterText(
      find.byKey(const ValueKey('user-broker-kis-product-code')),
      '01',
    );
    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-save')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-save')));
    await tester.pumpAndSettle();

    expect(api.savedProviders, contains('kis'));
    expect(api.savedCredentials.single['hts_id'], 'user-hts-id');
    expect(find.text('설정됨'), findsOneWidget);
    expect(find.text('HTS ID: ****-hts'), findsOneWidget);
    expect(
      tester
          .widget<TextField>(
            find.byKey(const ValueKey('user-broker-kis-app-secret')),
          )
          .controller!
          .text,
      isEmpty,
    );

    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-validate')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-validate')));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 1);
    expect(find.text('연결 확인됨'), findsOneWidget);

    await tester.ensureVisible(
      find.byKey(const ValueKey('user-broker-kis-remove')),
    );
    await tester.tap(find.byKey(const ValueKey('user-broker-kis-remove')));
    await tester.pumpAndSettle();

    expect(api.removeCalls, 1);
    expect(find.text('미설정'), findsNWidgets(2));
  });
}

Future<void> _pumpScreen(WidgetTester tester, _BrokerSettingsApi api) async {
  await tester.binding.setSurfaceSize(const Size(800, 1400));
  addTearDown(() async {
    await tester.binding.setSurfaceSize(null);
  });
  await tester.pumpWidget(
    MaterialApp(
      home: UserSettingsScreen(
        apiClient: api,
        user: const AuthUser(
          username: 'regular-user',
          role: 'user',
          enabled: true,
          setupCompleted: true,
        ),
        onLogout: () async {},
      ),
    ),
  );
  await tester.pumpAndSettle();
}

OutlinedButton _validateButton(WidgetTester tester, String provider) {
  return tester.widget<OutlinedButton>(
    find.byKey(ValueKey('user-broker-$provider-validate')),
  );
}

TextField _textField(WidgetTester tester, String key) {
  return tester.widget<TextField>(find.byKey(ValueKey(key)));
}

void _expectFieldsEmpty(WidgetTester tester, Iterable<String> keys) {
  for (final key in keys) {
    expect(_textField(tester, key).controller!.text, isEmpty);
  }
}

Future<void> _fillKis(WidgetTester tester) async {
  const values = {
    'user-broker-kis-app-key': 'user-app-key',
    'user-broker-kis-app-secret': 'user-app-secret',
    'user-broker-kis-hts-id': 'user-hts-id',
    'user-broker-kis-account-no': '12345678',
    'user-broker-kis-product-code': '01',
  };
  for (final entry in values.entries) {
    await tester.enterText(find.byKey(ValueKey(entry.key)), entry.value);
  }
}

Future<void> _fillAlpaca(WidgetTester tester) async {
  await tester.enterText(
    find.byKey(const ValueKey('user-broker-alpaca-api-key')),
    'user-api-key',
  );
  await tester.enterText(
    find.byKey(const ValueKey('user-broker-alpaca-secret-key')),
    'user-secret-key',
  );
}

class _BrokerSettingsApi extends ApiClient {
  _BrokerSettingsApi({Set<String> configuredProviders = const {}}) {
    for (final provider in configuredProviders) {
      _saved[provider] = _configured(provider);
    }
  }

  final Map<String, UserBrokerCredential> _saved = {};
  final List<String> savedProviders = [];
  final List<Map<String, dynamic>> savedCredentials = [];
  int validationCalls = 0;
  final List<String> validationRequests = [];
  int removeCalls = 0;

  @override
  Future<Map<String, dynamic>> fetchUserSettings() async => {};

  @override
  Future<List<UserWatchlistItem>> fetchUserWatchlist() async => [];

  @override
  Future<List<UserBrokerCredential>> fetchUserBrokers() async => [
        'kis',
        'alpaca'
      ].map((provider) => _saved[provider] ?? _empty(provider)).toList();

  @override
  Future<UserBrokerCredential> saveUserBroker(
    String provider,
    Map<String, dynamic> credentials,
  ) async {
    savedProviders.add(provider);
    savedCredentials.add(credentials);
    final saved = UserBrokerCredential(
      provider: provider,
      configured: true,
      environment: credentials['environment']?.toString() ?? 'paper',
      appKeyMasked: provider == 'kis' ? '****-key' : null,
      htsIdMasked: provider == 'kis' ? '****-hts' : null,
      accountNoMasked: provider == 'kis' ? '****5678' : null,
      apiKeyMasked: provider == 'alpaca' ? '****-key' : null,
      secretConfigured: true,
      appSecretConfigured: provider == 'kis',
      secretKeyConfigured: provider == 'alpaca',
    );
    _saved[provider] = saved;
    return saved;
  }

  @override
  Future<Map<String, dynamic>> validateUserBroker(String provider) async {
    validationCalls += 1;
    validationRequests.add(provider);
    final current = _saved[provider]!;
    _saved[provider] = current.withValidation(status: 'success', error: null);
    return {
      'provider': provider,
      'valid': true,
      'status': 'success',
      'message': null,
    };
  }

  @override
  Future<void> removeUserBroker(String provider) async {
    removeCalls += 1;
    _saved.remove(provider);
  }

  static UserBrokerCredential _configured(String provider) {
    return UserBrokerCredential(
      provider: provider,
      configured: true,
      environment: 'paper',
      appKeyMasked: provider == 'kis' ? '****-key' : null,
      htsIdMasked: provider == 'kis' ? '****-hts' : null,
      accountNoMasked: provider == 'kis' ? '****5678' : null,
      apiKeyMasked: provider == 'alpaca' ? '****-key' : null,
      secretConfigured: true,
      appSecretConfigured: provider == 'kis',
      secretKeyConfigured: provider == 'alpaca',
    );
  }

  static UserBrokerCredential _empty(String provider) {
    return UserBrokerCredential(provider: provider, configured: false);
  }
}
