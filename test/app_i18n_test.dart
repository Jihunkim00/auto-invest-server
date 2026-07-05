import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/i18n/app_strings.dart';

void main() {
  test('AppLanguage defaults unknown values to Korean', () {
    expect(appLanguageFromCode(null), AppLanguage.korean);
    expect(appLanguageFromCode('ko-KR'), AppLanguage.korean);
    expect(appLanguageFromCode('en-US'), AppLanguage.english);
  });

  test('AppStrings maps brokers and statuses by language', () {
    final ko = AppStrings(AppLanguage.korean);
    final en = AppStrings(AppLanguage.english);

    expect(ko.brokerName('kis'), '한국투자증권');
    expect(ko.brokerName('alpaca'), '알파카');
    expect(en.brokerName('kis'), 'KIS');
    expect(en.brokerName('alpaca'), 'Alpaca');
    expect(ko.statusLabel('sync_required'), '동기화 필요');
    expect(ko.statusLabel('review_required'), '검토 필요');
    expect(en.statusLabel('sync_required'), 'SYNC REQUIRED');
    expect(en.statusLabel('review_required'), 'REVIEW REQUIRED');
    expect(ko.preflightLiveBuy, '매수 전환 사전 점검');
    expect(ko.noLiveOrderSubmitted, '실주문 없음');
    expect(en.preflightLiveBuy, 'Preflight Live Buy');
    expect(en.noLiveOrderSubmitted, 'No Live Order Submitted');
    expect(ko.positionExitReview, '포지션 청산 검토');
    expect(ko.sellPreflight, '매도 사전 점검');
    expect(ko.noBrokerSubmitDisplay, '브로커 제출 없음');
    expect(en.positionExitReview, 'Position Exit Review');
    expect(en.sellPreflight, 'Sell Preflight');
    expect(en.noBrokerSubmitDisplay, 'No Broker Submit');
    expect(en.operatorAlertCenter, 'Operator Alert Center');
    expect(en.riskAlerts, 'Risk Alerts');
    expect(en.rejectedOrder, 'Rejected Order');
    expect(en.operatorReadOnly, 'Read Only');
    expect(en.operatorNoLiveOrders, 'No Live Orders');
    expect(ko.operatorAlertCenter, isNotEmpty);
    expect(ko.riskAlerts, isNotEmpty);
  });
}
