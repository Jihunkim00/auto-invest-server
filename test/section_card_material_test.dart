import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/widgets/section_card.dart';

void main() {
  testWidgets('SectionCard provides Material ancestry for tile widgets',
      (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: SectionCard(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                ListTile(
                  title: const Text('List tile'),
                  onTap: () {},
                ),
                SwitchListTile(
                  title: const Text('Switch tile'),
                  value: true,
                  onChanged: (_) {},
                ),
                const ExpansionTile(
                  title: Text('Expansion tile'),
                  children: [
                    ListTile(title: Text('Nested tile')),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);

    await tester.tap(find.text('Expansion tile'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('Nested tile'), findsOneWidget);
  });
}
