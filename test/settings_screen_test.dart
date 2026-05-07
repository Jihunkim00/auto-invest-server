import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/settings/settings_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';

void main() {
  testWidgets('dry-run switch success persists and refreshes settings',
      (tester) async {
    final api = _SettingsFakeApiClient(refreshedDryRun: false);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(controller));

    expect(_dryRunTile(tester).value, isTrue);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Dry Run'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate, {'dry_run': false});
    expect(api.getOpsSettingsCalls, 1);
    expect(controller.settings.dryRun, isFalse);
    expect(_dryRunTile(tester).value, isFalse);
    expect(
      find.descendant(
        of: find.byType(SnackBar),
        matching: find.text('Dry run disabled successfully.'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('dry-run switch failure rolls back and refreshes settings',
      (tester) async {
    final api = _SettingsFakeApiClient(throwUpdateOpsSettings: true);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(controller));

    expect(_dryRunTile(tester).value, isTrue);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Dry Run'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate, {'dry_run': false});
    expect(api.getOpsSettingsCalls, 1);
    expect(controller.settings.dryRun, isTrue);
    expect(_dryRunTile(tester).value, isTrue);
    expect(
      find.descendant(
        of: find.byType(SnackBar),
        matching: find.textContaining('Dry run update failed:'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: SettingsScreen(controller: controller)),
  );
}

SwitchListTile _dryRunTile(WidgetTester tester) {
  return tester.widget<SwitchListTile>(
    find.widgetWithText(SwitchListTile, 'Dry Run'),
  );
}

class _SettingsFakeApiClient extends ApiClient {
  _SettingsFakeApiClient({
    this.refreshedDryRun = true,
    this.throwUpdateOpsSettings = false,
  });

  final bool refreshedDryRun;
  final bool throwUpdateOpsSettings;
  int getOpsSettingsCalls = 0;
  int updateOpsSettingsCalls = 0;
  Map<String, dynamic>? lastSettingsUpdate;

  @override
  Future<OpsSettings> getOpsSettings() async {
    getOpsSettingsCalls += 1;
    return OpsSettings(
      schedulerEnabled: false,
      botEnabled: false,
      dryRun: refreshedDryRun,
      killSwitch: false,
      brokerMode: 'Paper',
      defaultGateLevel: 2,
      maxDailyTrades: 5,
      maxDailyEntries: 2,
      minEntryScore: 65,
      minScoreGap: 3,
    );
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    updateOpsSettingsCalls += 1;
    lastSettingsUpdate = values;
    if (throwUpdateOpsSettings) {
      throw const ApiRequestException(
        'HTTP 500: {"message":"settings failed"}',
      );
    }
  }

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    return KisManualOrderSafetyStatus(
      runtimeDryRun: refreshedDryRun,
      killSwitch: false,
      kisEnabled: true,
      kisRealOrderEnabled: true,
      marketOpen: true,
      entryAllowedNow: true,
      noNewEntryAfter: '15:00',
    );
  }
}
