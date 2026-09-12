import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../models/auth_session.dart';
import '../../models/user_broker_credential.dart';
import '../../models/user_watchlist_item.dart';

class UserSettingsScreen extends StatefulWidget {
  const UserSettingsScreen({
    super.key,
    required this.apiClient,
    required this.user,
    required this.onLogout,
  });

  final ApiClient apiClient;
  final AuthUser user;
  final Future<void> Function() onLogout;

  @override
  State<UserSettingsScreen> createState() => _UserSettingsScreenState();
}

class _UserPasswordDialog extends StatefulWidget {
  const _UserPasswordDialog({required this.apiClient});

  final ApiClient apiClient;

  @override
  State<_UserPasswordDialog> createState() => _UserPasswordDialogState();
}

class _UserPasswordDialogState extends State<_UserPasswordDialog> {
  final _currentController = TextEditingController();
  final _newController = TextEditingController();
  final _confirmController = TextEditingController();
  String? _error;
  bool _loading = false;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_newController.text.isEmpty ||
        _newController.text != _confirmController.text) {
      setState(() => _error = '새 비밀번호를 확인해 주세요.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await widget.apiClient.changePassword(
        currentPassword: _currentController.text,
        newPassword: _newController.text,
        confirmPassword: _confirmController.text,
      );
      if (mounted) Navigator.of(context).pop(true);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      key: const ValueKey('user-password-dialog'),
      title: const Text('비밀번호 변경'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            key: const ValueKey('user-current-password-field'),
            controller: _currentController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '현재 비밀번호'),
          ),
          TextField(
            key: const ValueKey('user-new-password-field'),
            controller: _newController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '새 비밀번호'),
          ),
          TextField(
            key: const ValueKey('user-confirm-password-field'),
            controller: _confirmController,
            obscureText: true,
            decoration: const InputDecoration(labelText: '새 비밀번호 확인'),
          ),
          if (_error != null)
            Text(_error!, style: const TextStyle(color: Colors.redAccent)),
        ],
      ),
      actions: [
        TextButton(
          onPressed: _loading ? null : () => Navigator.of(context).pop(),
          child: const Text('취소'),
        ),
        FilledButton(
          key: const ValueKey('user-password-submit'),
          onPressed: _loading ? null : _submit,
          child: const Text('변경'),
        ),
      ],
    );
  }
}

class _UserSettingsScreenState extends State<UserSettingsScreen> {
  final _displayNameController = TextEditingController();
  final _symbolController = TextEditingController();
  Map<String, dynamic> _settings = <String, dynamic>{};
  List<UserWatchlistItem> _watchlist = const [];
  String? _error;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _displayNameController.dispose();
    _symbolController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final values = await widget.apiClient.fetchUserSettings();
      final items = await widget.apiClient.fetchUserWatchlist();
      if (!mounted) return;
      setState(() {
        _settings = values;
        _watchlist = items;
        _loading = false;
      });
      _displayNameController.text = values['display_name']?.toString() ?? '';
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    try {
      final values = <String, dynamic>{
        ..._settings,
        'display_name': _displayNameController.text.trim(),
      };
      final saved = await widget.apiClient.updateUserSettings(values);
      if (!mounted) return;
      setState(() {
        _settings = saved;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('설정이 저장되었습니다.')),
      );
    } catch (error) {
      if (mounted) setState(() => _saving = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    }
  }

  Future<void> _addSymbol() async {
    final symbol = _symbolController.text.trim();
    if (symbol.isEmpty) return;
    try {
      final item = await widget.apiClient.addUserWatchlist(symbol: symbol);
      if (!mounted) return;
      setState(() {
        _watchlist = [..._watchlist, item];
        _symbolController.clear();
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    }
  }

  Future<void> _removeSymbol(String symbol) async {
    try {
      await widget.apiClient.removeUserWatchlist(symbol);
      if (mounted) {
        setState(() {
          _watchlist =
              _watchlist.where((item) => item.symbol != symbol).toList();
        });
      }
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(error.toString())),
        );
      }
    }
  }

  Future<void> _changePassword() async {
    final changed = await showDialog<bool>(
      context: context,
      builder: (_) => _UserPasswordDialog(apiClient: widget.apiClient),
    );
    if (changed == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('비밀번호가 변경되었습니다.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: const ValueKey('user-settings-screen'),
      appBar: AppBar(title: const Text('\uC124\uC815')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  key: const ValueKey('user-account-card'),
                  child: ListTile(
                    leading: const Icon(Icons.account_circle_outlined),
                    title: Text(widget.user.username),
                    subtitle: const Text('일반 사용자 · 운영 기능은 관리자만 사용할 수 있습니다.'),
                  ),
                ),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 10),
                    child: Text(
                      _error!,
                      key: const ValueKey('user-settings-error'),
                      style: const TextStyle(color: Colors.orangeAccent),
                    ),
                  ),
                const SizedBox(height: 12),
                Card(
                  key: const ValueKey('user-settings-card'),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          '내 설정',
                          style: TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          key: const ValueKey(
                              'user-settings-display-name-field'),
                          controller: _displayNameController,
                          decoration: const InputDecoration(
                            labelText: '표시 이름',
                            prefixIcon: Icon(Icons.badge_outlined),
                          ),
                        ),
                        const SizedBox(height: 12),
                        FilledButton.icon(
                          key: const ValueKey('user-settings-save-button'),
                          onPressed: _saving ? null : _save,
                          icon: const Icon(Icons.save_outlined),
                          label: Text(_saving ? '저장 중...' : '설정 저장'),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                _UserTradingSettingsCard(apiClient: widget.apiClient),
                const SizedBox(height: 12),
                _UserBrokerConnectionsCard(apiClient: widget.apiClient),
                const SizedBox(height: 12),
                Card(
                  key: const ValueKey('user-watchlist-card'),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          '내 관심종목',
                          style: TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: TextField(
                                key: const ValueKey(
                                    'user-watchlist-symbol-field'),
                                controller: _symbolController,
                                decoration: const InputDecoration(
                                  labelText: '종목 코드',
                                  hintText: '예: 005930',
                                ),
                                onSubmitted: (_) => _addSymbol(),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton(
                              key: const ValueKey('user-watchlist-add-button'),
                              onPressed: _addSymbol,
                              icon: const Icon(Icons.add_circle_outline),
                            ),
                          ],
                        ),
                        ..._watchlist.map(
                          (item) => ListTile(
                            key: ValueKey('user-watchlist-item-${item.symbol}'),
                            contentPadding: EdgeInsets.zero,
                            title: Text(item.symbol),
                            subtitle: Text('${item.provider} · ${item.market}'),
                            trailing: IconButton(
                              key: ValueKey(
                                  'user-watchlist-remove-${item.symbol}'),
                              onPressed: () => _removeSymbol(item.symbol),
                              icon: const Icon(Icons.remove_circle_outline),
                            ),
                          ),
                        ),
                        if (_watchlist.isEmpty)
                          const Text(
                            '등록된 관심종목이 없습니다.',
                            style: TextStyle(color: Colors.white70),
                          ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Card(
                  key: const ValueKey('user-account-actions-card'),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: [
                        OutlinedButton.icon(
                          key: const ValueKey('user-change-password-button'),
                          onPressed: _changePassword,
                          icon: const Icon(Icons.lock_reset_outlined),
                          label: const Text('비밀번호 변경'),
                        ),
                        FilledButton.icon(
                          key: const ValueKey('user-logout-button'),
                          onPressed: widget.onLogout,
                          icon: const Icon(Icons.logout),
                          label: const Text('로그아웃'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class _UserTradingSettingsCard extends StatefulWidget {
  const _UserTradingSettingsCard({required this.apiClient});

  final ApiClient apiClient;

  @override
  State<_UserTradingSettingsCard> createState() =>
      _UserTradingSettingsCardState();
}

class _UserTradingSettingsCardState extends State<_UserTradingSettingsCard> {
  final _dailyTrades = TextEditingController();
  final _dailyLoss = TextEditingController();
  final _positionPct = TextEditingController();
  final _openPositions = TextEditingController();
  String _mode = 'paper';
  bool _liveTradingEnabled = false;
  bool _killSwitch = true;
  String? _error;
  bool _loading = true;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _dailyTrades.dispose();
    _dailyLoss.dispose();
    _positionPct.dispose();
    _openPositions.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final values = await widget.apiClient.fetchUserTradingSettings();
      if (!mounted) return;
      setState(() {
        _mode = values['trading_mode']?.toString() == 'live' ? 'live' : 'paper';
        _liveTradingEnabled = values['live_trading_enabled'] == true;
        _killSwitch = values['kill_switch'] != false;
        _dailyTrades.text = '${values['max_daily_trades'] ?? 2}';
        _dailyLoss.text = '${values['max_daily_loss_pct'] ?? 0.02}';
        _positionPct.text = '${values['max_position_pct'] ?? 10}';
        _openPositions.text = '${values['max_open_positions'] ?? 1}';
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = '거래 설정을 불러오지 못했습니다.';
      });
    }
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final saved = await widget.apiClient.updateUserTradingSettings(
        tradingMode: _mode,
        maxDailyTrades: int.tryParse(_dailyTrades.text.trim()),
        maxDailyLossPct: double.tryParse(_dailyLoss.text.trim()),
        maxPositionPct: double.tryParse(_positionPct.text.trim()),
        maxOpenPositions: int.tryParse(_openPositions.text.trim()),
        liveTradingEnabled: _liveTradingEnabled,
        killSwitch: _killSwitch,
      );
      if (!mounted) return;
      setState(() {
        _mode = saved['trading_mode']?.toString() == 'live' ? 'live' : 'paper';
        _liveTradingEnabled = saved['live_trading_enabled'] == true;
        _killSwitch = saved['kill_switch'] != false;
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('거래 설정이 저장되었습니다.')),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = '거래 설정을 저장하지 못했습니다.';
      });
    }
  }

  Future<void> _toggleLiveTrading(bool value) async {
    if (!value) {
      setState(() => _liveTradingEnabled = false);
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('실거래 주문 사용'),
        content: const Text(
          '실거래를 활성화하면 실제 자금으로 주문이 전송될 수 있습니다.\n계속하시겠습니까?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('실거래 활성화'),
          ),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      setState(() => _liveTradingEnabled = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const ValueKey('user-trading-settings-card'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    '거래 모드',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  ToggleButtons(
                    isSelected: [_mode == 'paper', _mode == 'live'],
                    onPressed: _saving
                        ? null
                        : (index) => setState(
                              () => _mode = index == 0 ? 'paper' : 'live',
                            ),
                    children: const [
                      Padding(
                        padding: EdgeInsets.symmetric(horizontal: 16),
                        child: Text('모의투자'),
                      ),
                      Padding(
                        padding: EdgeInsets.symmetric(horizontal: 16),
                        child: Text('실거래'),
                      ),
                    ],
                  ),
                  if (_mode == 'live') ...[
                    const SizedBox(height: 12),
                    SwitchListTile(
                      key: const ValueKey('user-live-trading-enabled'),
                      contentPadding: EdgeInsets.zero,
                      title: const Text('실거래 주문 사용'),
                      subtitle: Text(
                        _liveTradingEnabled ? '실거래 주문 사용 가능' : '실거래 주문 비활성화',
                      ),
                      value: _liveTradingEnabled,
                      onChanged: _saving
                          ? null
                          : (value) => unawaited(_toggleLiveTrading(value)),
                    ),
                    SwitchListTile(
                      key: const ValueKey('user-kill-switch'),
                      contentPadding: EdgeInsets.zero,
                      title: const Text('긴급 정지'),
                      subtitle: Text(
                        _killSwitch ? '긴급 정지 활성화 · 신규 실거래 차단' : '긴급 정지 해제',
                      ),
                      value: _killSwitch,
                      onChanged: _saving
                          ? null
                          : (value) => setState(() => _killSwitch = value),
                    ),
                  ],
                  const SizedBox(height: 16),
                  const Text(
                    '리스크 설정',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 8),
                  _riskField(
                    key: const ValueKey('user-max-daily-trades'),
                    controller: _dailyTrades,
                    label: '일일 최대 거래 횟수',
                  ),
                  _riskField(
                    key: const ValueKey('user-max-daily-loss-pct'),
                    controller: _dailyLoss,
                    label: '일일 최대 손실률',
                  ),
                  _riskField(
                    key: const ValueKey('user-max-position-pct'),
                    controller: _positionPct,
                    label: '최대 포지션 비중',
                  ),
                  _riskField(
                    key: const ValueKey('user-max-open-positions'),
                    controller: _openPositions,
                    label: '최대 보유 종목 수',
                  ),
                  if (_error != null)
                    Text(_error!,
                        style: const TextStyle(color: Colors.orangeAccent)),
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    key: const ValueKey('user-trading-settings-save'),
                    onPressed: _saving ? null : _save,
                    icon: const Icon(Icons.save_outlined),
                    label: Text(_saving ? '저장 중...' : '거래 설정 저장'),
                  ),
                ],
              ),
      ),
    );
  }

  Widget _riskField({
    required Key key,
    required TextEditingController controller,
    required String label,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
        key: key,
        controller: controller,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(labelText: label),
      ),
    );
  }
}

class _UserBrokerConnectionsCard extends StatefulWidget {
  const _UserBrokerConnectionsCard({required this.apiClient});

  final ApiClient apiClient;

  @override
  State<_UserBrokerConnectionsCard> createState() =>
      _UserBrokerConnectionsCardState();
}

class _UserBrokerConnectionsCardState
    extends State<_UserBrokerConnectionsCard> {
  final _kisAppKey = TextEditingController();
  final _kisAppSecret = TextEditingController();
  final _kisHtsId = TextEditingController();
  final _kisAccountNo = TextEditingController();
  final _kisProductCode = TextEditingController();
  final _alpacaApiKey = TextEditingController();
  final _alpacaSecretKey = TextEditingController();

  final Map<String, UserBrokerCredential> _brokers = {};
  String _kisEnvironment = 'paper';
  String _alpacaEnvironment = 'paper';
  String? _busyProvider;
  String? _busyOperation;
  String? _message;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _kisAppKey.dispose();
    _kisAppSecret.dispose();
    _kisHtsId.dispose();
    _kisAccountNo.dispose();
    _kisProductCode.dispose();
    _alpacaApiKey.dispose();
    _alpacaSecretKey.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final values = await widget.apiClient.fetchUserBrokers();
      if (!mounted) return;
      setState(() {
        _brokers
          ..clear()
          ..addEntries(values.map((item) => MapEntry(item.provider, item)));
        _kisEnvironment = _status('kis').environment ?? 'paper';
        _alpacaEnvironment = _status('alpaca').environment ?? 'paper';
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _message = _safeError(error);
      });
    }
  }

  UserBrokerCredential _status(String provider) {
    return _brokers[provider] ??
        UserBrokerCredential(
          provider: provider,
          configured: false,
        );
  }

  Future<void> _saveKis() async {
    await _save(
      'kis',
      {
        'environment': _kisEnvironment,
        'app_key': _kisAppKey.text.trim(),
        'app_secret': _kisAppSecret.text,
        'hts_id': _kisHtsId.text.trim(),
        'account_no': _kisAccountNo.text.trim(),
        'account_product_code': _kisProductCode.text.trim(),
      },
    );
  }

  Future<void> _saveAlpaca() async {
    await _save(
      'alpaca',
      {
        'environment': _alpacaEnvironment,
        'api_key': _alpacaApiKey.text.trim(),
        'secret_key': _alpacaSecretKey.text,
      },
    );
  }

  Future<void> _save(
    String provider,
    Map<String, dynamic> values,
  ) async {
    if (values.values.any((value) => value.toString().trim().isEmpty)) {
      _showMessage('모든 입력 항목을 입력한 후 저장하세요.', error: true);
      return;
    }
    setState(() {
      _busyProvider = provider;
      _busyOperation = 'save';
      _message = null;
    });
    try {
      final saved = await widget.apiClient.saveUserBroker(provider, values);
      if (!mounted) return;
      setState(() {
        _brokers[provider] = saved;
        _busyProvider = null;
        _busyOperation = null;
        _message = '${_providerLabel(provider)} 정보가 저장되었습니다.';
      });
      _clearSecretInputs(provider);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _busyProvider = null;
        _busyOperation = null;
        _message = _safeError(error);
      });
    }
  }

  Future<void> _validate(String provider) async {
    setState(() {
      _busyProvider = provider;
      _busyOperation = 'validate';
      _message = null;
    });
    try {
      final result = await widget.apiClient.validateUserBroker(provider);
      final valid = result['valid'] == true;
      final status = _status(provider);
      if (!mounted) return;
      setState(() {
        _brokers[provider] = status.withValidation(
          status: result['status']?.toString(),
          error: valid
              ? null
              : result['message']?.toString() ?? 'validation_failed',
        );
        _busyProvider = null;
        _busyOperation = null;
        _message = valid
            ? '${_providerLabel(provider)} 연결이 확인되었습니다.'
            : '연결 확인 실패: ${_validationMessage(result['message'])}';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _busyProvider = null;
        _busyOperation = null;
        _message = _safeError(error);
      });
    }
  }

  Future<void> _remove(String provider) async {
    setState(() {
      _busyProvider = provider;
      _busyOperation = 'remove';
      _message = null;
    });
    try {
      await widget.apiClient.removeUserBroker(provider);
      if (!mounted) return;
      setState(() {
        _brokers.remove(provider);
        _busyProvider = null;
        _busyOperation = null;
        _message = '${_providerLabel(provider)} 정보가 삭제되었습니다.';
      });
      _clearInputs(provider);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _busyProvider = null;
        _busyOperation = null;
        _message = _safeError(error);
      });
    }
  }

  void _clearSecretInputs(String provider) {
    if (provider == 'kis') {
      _kisAppKey.clear();
      _kisAppSecret.clear();
      _kisHtsId.clear();
      _kisAccountNo.clear();
      _kisProductCode.clear();
    } else {
      _alpacaApiKey.clear();
      _alpacaSecretKey.clear();
    }
  }

  void _clearInputs(String provider) {
    _clearSecretInputs(provider);
    setState(() {
      if (provider == 'kis') {
        _kisEnvironment = 'paper';
      } else {
        _alpacaEnvironment = 'paper';
      }
    });
  }

  void _showMessage(String message, {bool error = false}) {
    setState(() => _message = message);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: error ? Colors.redAccent : Colors.green,
      ),
    );
  }

  String _safeError(Object error) {
    if (error is ApiRequestException) return '브로커 요청에 실패했습니다.';
    return '브로커 요청에 실패했습니다.';
  }

  String _validationMessage(Object? message) {
    switch (message?.toString()) {
      case 'invalid_credentials':
        return '입력 정보를 확인하세요.';
      case 'authentication_failed':
        return '인증에 실패했습니다.';
      case 'account_query_failed':
        return '계좌 정보를 확인하지 못했습니다.';
      case 'network_error':
        return '네트워크 오류가 발생했습니다.';
      default:
        return '알 수 없는 오류입니다.';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      key: const ValueKey('user-broker-connections-card'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '증권사 연결',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            const Text(
              '입력 정보는 서버에서 암호화되며 전체 값은 다시 표시되지 않습니다.',
              style: TextStyle(color: Colors.white70),
            ),
            if (_loading)
              const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator()),
              )
            else ...[
              const SizedBox(height: 16),
              _buildKis(),
              const Divider(height: 32),
              _buildAlpaca(),
              if (_message != null) ...[
                const SizedBox(height: 12),
                Text(
                  _message!,
                  key: const ValueKey('user-broker-message'),
                  style: TextStyle(
                    color: _message!.contains('실패') || _message!.contains('입력')
                        ? Colors.orangeAccent
                        : Colors.greenAccent,
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildKis() {
    final status = _status('kis');
    final busy = _busyProvider == 'kis';
    return _providerSection(
      provider: 'kis',
      title: '한국투자증권',
      helpText: '한국투자증권 Open API에서 발급받은 정보를 입력하세요.',
      status: status,
      busy: busy,
      environment: _kisEnvironment,
      onEnvironmentChanged: (value) => setState(() => _kisEnvironment = value),
      children: [
        _credentialField(
          key: const ValueKey('user-broker-kis-app-key'),
          controller: _kisAppKey,
          label: '앱 키',
          helperText:
              status.configured ? '저장된 정보를 변경하려면 모든 값을 새로 입력하세요.' : null,
        ),
        _credentialField(
          key: const ValueKey('user-broker-kis-app-secret'),
          controller: _kisAppSecret,
          label: '앱 시크릿',
          obscureText: true,
        ),
        _credentialField(
          key: const ValueKey('user-broker-kis-hts-id'),
          controller: _kisHtsId,
          label: 'HTS ID',
        ),
        _credentialField(
          key: const ValueKey('user-broker-kis-account-no'),
          controller: _kisAccountNo,
          label: '계좌번호',
        ),
        _credentialField(
          key: const ValueKey('user-broker-kis-product-code'),
          controller: _kisProductCode,
          label: '계좌 상품코드',
        ),
      ],
    );
  }

  Widget _buildAlpaca() {
    final status = _status('alpaca');
    final busy = _busyProvider == 'alpaca';
    return _providerSection(
      provider: 'alpaca',
      title: 'Alpaca',
      helpText: 'Alpaca에서 발급받은 API 정보를 입력하세요.',
      status: status,
      busy: busy,
      environment: _alpacaEnvironment,
      onEnvironmentChanged: (value) =>
          setState(() => _alpacaEnvironment = value),
      children: [
        _credentialField(
          key: const ValueKey('user-broker-alpaca-api-key'),
          controller: _alpacaApiKey,
          label: 'API 키',
          helperText:
              status.configured ? '저장된 정보를 변경하려면 두 값을 모두 새로 입력하세요.' : null,
        ),
        _credentialField(
          key: const ValueKey('user-broker-alpaca-secret-key'),
          controller: _alpacaSecretKey,
          label: '시크릿 키',
          obscureText: true,
        ),
      ],
    );
  }

  Widget _providerSection({
    required String provider,
    required String title,
    required UserBrokerCredential status,
    required bool busy,
    required String environment,
    required String helpText,
    required ValueChanged<String> onEnvironmentChanged,
    required List<Widget> children,
  }) {
    final color = status.validated
        ? Colors.greenAccent
        : status.configured
            ? Colors.lightBlueAccent
            : Colors.white70;
    // Stored credentials are intentionally never restored into the fields.
    // Validation uses the encrypted credential kept by the backend.
    final canValidate = status.configured && !busy;
    final statusLabel = !status.configured
        ? '미설정'
        : status.validated
            ? '연결 확인됨'
            : '설정됨';

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                title,
                style:
                    const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
              ),
            ),
            Chip(
              key: ValueKey('user-broker-$provider-status'),
              label: Text(statusLabel),
              labelStyle: TextStyle(color: color),
            ),
          ],
        ),
        Text(helpText, style: const TextStyle(color: Colors.white70)),
        const SizedBox(height: 4),
        if (status.configured) ...[
          if (provider == 'kis') ...[
            Text('앱 키: ${status.appKeyMasked ?? '설정됨'}'),
            Text('HTS ID: ${status.htsIdMasked ?? '설정됨'}'),
            Text('계좌번호: ${status.accountNoMasked ?? '설정됨'}'),
            const Text('앱 시크릿: 시크릿 설정됨'),
          ] else ...[
            Text('API 키: ${status.apiKeyMasked ?? '설정됨'}'),
            const Text('시크릿 키: 시크릿 설정됨'),
          ],
          if (status.lastValidationError != null)
            Text(
              '연결 확인 오류: ${_validationMessage(status.lastValidationError)}',
              style: const TextStyle(color: Colors.orangeAccent),
            ),
          const SizedBox(height: 8),
        ],
        DropdownButtonFormField<String>(
          key: ValueKey('user-broker-$provider-environment'),
          initialValue: environment,
          decoration: const InputDecoration(labelText: '거래 환경'),
          items: const [
            DropdownMenuItem(value: 'paper', child: Text('모의투자')),
            DropdownMenuItem(value: 'live', child: Text('실거래')),
          ],
          onChanged: busy
              ? null
              : (value) {
                  if (value != null) onEnvironmentChanged(value);
                },
        ),
        Text(
          environment == 'live'
              ? '실거래 환경입니다. API 정보를 정확히 확인하세요.'
              : '모의투자 환경입니다.',
          style: const TextStyle(color: Colors.white70),
        ),
        ...children,
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            FilledButton.icon(
              key: ValueKey('user-broker-$provider-save'),
              onPressed: busy
                  ? null
                  : () => provider == 'kis' ? _saveKis() : _saveAlpaca(),
              icon: const Icon(Icons.save_outlined),
              label: Text(
                busy && _busyOperation == 'save' ? '저장 중...' : '저장',
              ),
            ),
            OutlinedButton.icon(
              key: ValueKey('user-broker-$provider-validate'),
              onPressed: canValidate ? () => _validate(provider) : null,
              icon: const Icon(Icons.verified_outlined),
              label: Text(
                busy && _busyOperation == 'validate' ? '확인 중...' : '연결 확인',
              ),
            ),
            if (status.configured)
              OutlinedButton.icon(
                key: ValueKey('user-broker-$provider-remove'),
                onPressed: busy ? null : () => _remove(provider),
                icon: const Icon(Icons.delete_outline),
                label: Text(
                  busy && _busyOperation == 'remove' ? '삭제 중...' : '삭제',
                ),
              ),
          ],
        ),
      ],
    );
  }

  Widget _credentialField({
    required Key key,
    required TextEditingController controller,
    required String label,
    bool obscureText = false,
    String? helperText,
  }) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: TextField(
        key: key,
        controller: controller,
        obscureText: obscureText,
        enableSuggestions: !obscureText,
        autocorrect: !obscureText,
        decoration: InputDecoration(
          labelText: label,
          helperText: helperText,
        ),
      ),
    );
  }

  String _providerLabel(String provider) {
    return provider == 'kis' ? '한국투자증권' : 'Alpaca';
  }
}
