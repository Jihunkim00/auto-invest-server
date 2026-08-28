import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/broker_context_controls.dart';

void main() {
  testWidgets('Korean broker selector uses compact one-line labels',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..selectedProvider = SelectedProvider.alpaca
      ..selectedPortfolioMarket = PortfolioMarket.us
      ..selectedWatchlistMarket = PortfolioMarket.us
      ..selectedOrderMarket = PortfolioMarket.us;

    await tester.pumpWidget(_brokerSelectorHarness(controller));
    await tester.pumpAndSettle();

    expect(
        find.byKey(const ValueKey('global-broker-selector')), findsOneWidget);
    expect(find.byKey(const ValueKey('broker-option-alpaca')), findsOneWidget);
    expect(find.byKey(const ValueKey('broker-option-kis')), findsOneWidget);
    expect(find.text('알파카'), findsOneWidget);
    expect(find.text('한국투자'), findsOneWidget);
    expect(controller.selectedBrokerLabel, '알파카 / 미국');
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('global-broker-selector')),
        matching: find.text('한국투자증권'),
      ),
      findsNothing,
    );
    expect(find.textContaining('(KIS)'), findsNothing);

    final alpacaLabel = tester.widget<Text>(
      find.byKey(const ValueKey('broker-option-alpaca-label')),
    );
    final kisLabel = tester.widget<Text>(
      find.byKey(const ValueKey('broker-option-kis-label')),
    );
    expect(alpacaLabel.maxLines, 1);
    expect(alpacaLabel.overflow, isNot(TextOverflow.ellipsis));
    expect(kisLabel.maxLines, 1);
    expect(kisLabel.overflow, isNot(TextOverflow.ellipsis));
    expect(
      tester
          .getSize(find.byKey(const ValueKey('global-broker-selector')))
          .width,
      greaterThanOrEqualTo(230),
    );
    expect(
      tester
          .getSize(find.byKey(const ValueKey('global-broker-selector')))
          .height,
      greaterThanOrEqualTo(40),
    );
    expect(tester.takeException(), isNull);

    await tester.tap(find.byKey(const ValueKey('broker-option-kis-label')));
    await tester.pumpAndSettle();
    expect(controller.selectedProvider, SelectedProvider.kis);
    expect(controller.selectedBrokerLabel, '한국투자증권 / 국내');

    controller.dispose();
  });

  testWidgets('English broker selector keeps Alpaca and KIS labels',
      (tester) async {
    final controller = DashboardController(
      ApiClient(),
      autoload: false,
      initialLanguage: AppLanguage.english,
    )
      ..selectedProvider = SelectedProvider.alpaca
      ..selectedPortfolioMarket = PortfolioMarket.us
      ..selectedWatchlistMarket = PortfolioMarket.us
      ..selectedOrderMarket = PortfolioMarket.us;

    await tester.pumpWidget(_brokerSelectorHarness(controller, width: 280));
    await tester.pumpAndSettle();

    expect(find.text('Alpaca'), findsOneWidget);
    expect(find.text('KIS'), findsOneWidget);
    expect(controller.selectedBrokerLabel, 'Alpaca / US');
    expect(find.text('한국투자'), findsNothing);
    expect(find.text('한국투자증권'), findsNothing);

    final kisLabel = tester.widget<Text>(
      find.byKey(const ValueKey('broker-option-kis-label')),
    );
    expect(kisLabel.maxLines, 1);
    expect(kisLabel.overflow, isNot(TextOverflow.ellipsis));
    expect(tester.takeException(), isNull);

    controller.dispose();
  });

  testWidgets('Korean broker selector keeps full labels at 1.3 text scale',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..selectedPortfolioMarket = PortfolioMarket.kr
      ..selectedWatchlistMarket = PortfolioMarket.kr
      ..selectedOrderMarket = PortfolioMarket.kr;

    await tester.pumpWidget(
      _brokerSelectorHarness(controller, textScale: 1.3),
    );
    await tester.pumpAndSettle();

    expect(find.text('알파카'), findsOneWidget);
    expect(find.text('한국투자'), findsOneWidget);
    expect(find.textContaining('한국투...'), findsNothing);
    expect(tester.takeException(), isNull);
    controller.dispose();
  });
}

Widget _brokerSelectorHarness(
  DashboardController controller, {
  double? width,
  double? textScale,
}) {
  return MaterialApp(
    theme: ThemeData.dark(),
    builder: (context, child) {
      final scaledChild = textScale == null
          ? child!
          : MediaQuery(
              data: MediaQuery.of(context)
                  .copyWith(textScaler: TextScaler.linear(textScale)),
              child: child!,
            );
      return Center(child: scaledChild);
    },
    home: Scaffold(
      body: Center(
        child: width == null
            ? UnconstrainedBox(
                child: GlobalBrokerSelector(controller: controller),
              )
            : SizedBox(
                width: width,
                child: GlobalBrokerSelector(controller: controller),
              ),
      ),
    ),
  );
}
