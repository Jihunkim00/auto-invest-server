import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/i18n/app_strings.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/settings/settings_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/operation_mode.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';

void main() {
  testWidgets('Korean settings UI renders without mojibake', (tester) async {
    tester.view.physicalSize = const Size(1200, 3600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = DashboardController(
      _NoopApiClient(),
      autoload: false,
      initialLanguage: AppLanguage.korean,
    )
      ..selectedProvider = SelectedProvider.kis
      ..settings = _safeSettings
      ..operationModeStatus = OperationModeStatus.safeDefault
      ..schedulerStatus = SchedulerStatus.safeDefault()
      ..kisSafetyStatus = _safeKisStatus;

    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(body: SettingsScreen(controller: controller)),
      ),
    );
    await tester.pump();

    expect(find.text('설정'), findsOneWidget);
    expect(find.text('언어'), findsOneWidget);
    expect(find.text('한국투자증권 안전 상태와 수동 실거래 상태입니다.'), findsOneWidget);
    expect(find.text('Paper'), findsWidgets);

    final strings = AppStrings(AppLanguage.korean);
    for (final value in [
      strings.brokerSyncWatchdog,
      strings.positionLifecycle,
      strings.executeGuardedLiveSell,
    ]) {
      _expectNoMojibake(value);
    }

    controller.dispose();
  });
}

const _safeSettings = OpsSettings(
  schedulerEnabled: false,
  botEnabled: false,
  dryRun: true,
  killSwitch: false,
  brokerMode: 'Paper',
  defaultGateLevel: 2,
  maxDailyTrades: 5,
  maxDailyEntries: 2,
  minEntryScore: 65,
  minScoreGap: 3,
  currentOperationMode: 'paper',
);

const _safeKisStatus = KisManualOrderSafetyStatus(
  runtimeDryRun: true,
  killSwitch: false,
  kisEnabled: true,
  kisRealOrderEnabled: false,
  marketOpen: false,
  entryAllowedNow: false,
  noNewEntryAfter: '15:00',
);

void _expectNoMojibake(String value) {
  for (final marker in ['ì', 'ë', 'ê', String.fromCharCode(0xFFFD)]) {
    expect(value, isNot(contains(marker)));
  }
}

class _NoopApiClient extends ApiClient {}
