import '../../features/dashboard/dashboard_controller.dart';

enum AppTextKey { autoInvest, home, analysis, trading, logs, kisSubtitle, alpacaSubtitle, autoBuyOff, apiHealthy, todaySignal, confidence, preTradeCheck, recentEvents, orderReview, executeOrder, cancel, confirm, kisAnalyzeBuy, krSymbol, quantity, kisCheckbox, kisConfirmTitle, kisConfirmBody }

class AppStrings {
  static String t(AppTextKey key, UiLanguage language) {
    final ko = language == UiLanguage.ko;
    switch (key) {
      case AppTextKey.autoInvest:
        return ko ? '자동투자' : 'Auto Invest';
      case AppTextKey.home:
        return ko ? '홈' : 'Home';
      case AppTextKey.analysis:
        return ko ? '분석' : 'Analysis';
      case AppTextKey.trading:
        return ko ? '주문' : 'Trading';
      case AppTextKey.logs:
        return ko ? '로그' : 'Logs';
      case AppTextKey.kisSubtitle:
        return ko ? 'KIS 실전계좌 · 안전모드' : 'KIS live account · safety mode';
      case AppTextKey.alpacaSubtitle:
        return ko ? 'Alpaca 모의투자 · 안전모드' : 'Alpaca paper trading · safety mode';
      case AppTextKey.autoBuyOff:
        return ko ? '자동매수 OFF' : 'Auto Buy OFF';
      case AppTextKey.apiHealthy:
        return ko ? 'API 정상' : 'API Healthy';
      case AppTextKey.todaySignal:
        return ko ? '오늘의 추천 시그널' : 'Today\'s Signal';
      case AppTextKey.confidence:
        return ko ? '신뢰도' : 'Confidence';
      case AppTextKey.preTradeCheck:
        return ko ? '실행 전 체크' : 'Pre-trade Check';
      case AppTextKey.recentEvents:
        return ko ? '최근 이벤트' : 'Recent Events';
      case AppTextKey.orderReview:
        return ko ? '주문 검토' : 'Order Review';
      case AppTextKey.executeOrder:
        return ko ? '주문 실행' : 'Execute Order';
      case AppTextKey.cancel:
        return ko ? '취소' : 'Cancel';
      case AppTextKey.confirm:
        return ko ? '확인' : 'Confirm';
      case AppTextKey.kisAnalyzeBuy:
        return ko ? 'KIS 분석 후 매수' : 'KIS Analyze & Buy';
      case AppTextKey.krSymbol:
        return ko ? '국내 종목코드' : 'KR Symbol';
      case AppTextKey.quantity:
        return ko ? '수량' : 'Quantity';
      case AppTextKey.kisCheckbox:
        return ko ? '실제 KIS 주문이 제출될 수 있음을 확인했습니다.' : 'I understand that a real KIS order may be submitted.';
      case AppTextKey.kisConfirmTitle:
        return ko ? 'KIS 주문 확인' : 'Confirm KIS Order';
      case AppTextKey.kisConfirmBody:
        return ko ? '실제 KIS 주문이 제출될 수 있습니다. 실행 전 종목과 수량을 다시 확인하세요.' : 'A real KIS order may be submitted. Please review the symbol and quantity before execution.';
    }
  }
}
