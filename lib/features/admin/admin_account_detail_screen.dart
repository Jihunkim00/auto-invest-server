import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../../core/network/api_client.dart';
import '../../models/auth_session.dart';

class AdminAccountDetailScreen extends StatefulWidget {
  const AdminAccountDetailScreen(
      {super.key, required this.apiClient, required this.user});

  final ApiClient apiClient;
  final AuthUser user;

  @override
  State<AdminAccountDetailScreen> createState() =>
      _AdminAccountDetailScreenState();
}

class _AdminAccountDetailScreenState extends State<AdminAccountDetailScreen> {
  final _total = TextEditingController();
  final _position = TextEditingController();
  final _form = GlobalKey<FormState>();
  final _krw =
      NumberFormat.currency(locale: 'ko_KR', symbol: '₩', decimalDigits: 0);
  Map<String, dynamic>? _saved;
  Map<String, dynamic>? _usage;
  bool _totalUnlimited = false;
  bool _positionUnlimited = false;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _total.dispose();
    _position.dispose();
    super.dispose();
  }

  void _restore(Map<String, dynamic> limits) {
    _totalUnlimited = limits['max_total_exposure_krw'] == null;
    _positionUnlimited = limits['max_position_notional_krw'] == null;
    _total.text = _digits(limits['max_total_exposure_krw']);
    _position.text = _digits(limits['max_position_notional_krw']);
  }

  String _digits(Object? amount) =>
      amount is num ? NumberFormat('#,##0', 'ko_KR').format(amount) : '';
  double? _amount(TextEditingController controller) =>
      double.tryParse(controller.text.replaceAll(',', '').trim());

  Future<void> _load() async {
    final generation = ++_loadGeneration;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final detail =
          await widget.apiClient.fetchAdminAccountDetail(widget.user.id!);
      if (!mounted || generation != _loadGeneration) return;
      final limits = Map<String, dynamic>.from(detail['trading_limits'] as Map);
      setState(() {
        _saved = limits;
        _restore(limits);
        _loading = false;
        _usage = null;
      });
      unawaited(_loadUsage(generation));
    } catch (error) {
      if (!mounted || generation != _loadGeneration) return;
      setState(() {
        _loading = false;
        _error = error.toString();
      });
    }
  }

  Future<void> _loadUsage(int generation) async {
    Map<String, dynamic> usage;
    try {
      usage =
          await widget.apiClient.fetchAdminAccountLimitUsage(widget.user.id!);
    } catch (_) {
      usage = {'available': false};
    }
    if (mounted && generation == _loadGeneration)
      setState(() => _usage = usage);
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final detail = await widget.apiClient.updateAdminAccountTradingLimits(
        userId: widget.user.id!,
        maxTotalExposureKrw: _totalUnlimited ? null : _amount(_total),
        maxPositionNotionalKrw: _positionUnlimited ? null : _amount(_position),
      );
      if (!mounted) return;
      final limits = Map<String, dynamic>.from(detail['trading_limits'] as Map);
      setState(() {
        _saved = limits;
        _restore(limits);
        _saving = false;
        _loadGeneration++;
        _usage = null;
      });
      unawaited(_loadUsage(_loadGeneration));
    } catch (error) {
      if (!mounted) return;
      setState(() {
        if (_saved != null) _restore(_saved!);
        _saving = false;
        _error = error.toString();
      });
    }
  }

  Widget _limitField(
      {required String keyName,
      required String label,
      required TextEditingController controller,
      required bool unlimited,
      required ValueChanged<bool> onUnlimited}) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
      SwitchListTile(
        key: ValueKey('account-limit-$keyName-unlimited'),
        contentPadding: EdgeInsets.zero,
        title: const Text('제한 없음'),
        value: unlimited,
        onChanged: _saving ? null : onUnlimited,
      ),
      TextFormField(
        key: ValueKey('account-limit-$keyName-amount'),
        controller: controller,
        enabled: !unlimited && !_saving,
        keyboardType: TextInputType.number,
        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(r'[0-9,]'))],
        decoration: InputDecoration(
            prefixText: '₩ ', hintText: unlimited ? '제한 없음' : '금액 입력'),
        validator: (_) {
          if (unlimited) return null;
          final amount = _amount(controller);
          return amount == null || !amount.isFinite || amount <= 0
              ? '0보다 큰 금액을 입력하세요.'
              : null;
        },
      ),
      const SizedBox(height: 18),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    final usage = _usage;
    final saved = _saved;
    return Scaffold(
      key: const ValueKey('admin-account-detail'),
      appBar:
          AppBar(title: Text('${widget.user.username} · 계정 상세 설정'), actions: [
        IconButton(
            key: const ValueKey('account-limit-refresh'),
            onPressed: _saving ? null : _load,
            icon: const Icon(Icons.refresh)),
      ]),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(20),
              children: [
                const Text('거래 한도',
                    key: ValueKey('account-trading-limits-section'),
                    style:
                        TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                const Text(
                    'KIS 계정의 보유 평가금액 기준입니다. 자동화 프로필의 주문금액과 현금 한도도 함께 적용됩니다.'),
                const SizedBox(height: 20),
                if (_error != null)
                  Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(_error!,
                          key: const ValueKey('account-limit-error'))),
                if (saved != null)
                  Form(
                      key: _form,
                      child: Column(children: [
                        _limitField(
                            keyName: 'total',
                            label: '계정 총 투자 한도',
                            controller: _total,
                            unlimited: _totalUnlimited,
                            onUnlimited: (value) => setState(() {
                                  _totalUnlimited = value;
                                  if (!value && _total.text.isEmpty)
                                    _total.text = '10,000,000';
                                })),
                        _limitField(
                            keyName: 'position',
                            label: '종목당 최대 금액',
                            controller: _position,
                            unlimited: _positionUnlimited,
                            onUnlimited: (value) => setState(() {
                                  _positionUnlimited = value;
                                  if (!value && _position.text.isEmpty)
                                    _position.text = '1,000,000';
                                })),
                        FilledButton(
                            key: const ValueKey('account-limit-save'),
                            onPressed: _saving ? null : _save,
                            child: Text(_saving ? '저장 중…' : '저장')),
                      ])),
                const SizedBox(height: 28),
                const Text('현재 사용 현황',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 8),
                if (usage == null)
                  const Text('사용 현황 조회 중…')
                else if (usage['available'] != true)
                  const Text('현재 사용 현황을 조회할 수 없습니다. 한도 설정은 변경할 수 있습니다.')
                else ...[
                  Text(
                      '현재 총 투자금액: ${_krw.format(usage['current_account_exposure_krw'])} / ${saved?['max_total_exposure_krw'] == null ? '제한 없음' : _krw.format(saved!['max_total_exposure_krw'])}'),
                  Text(
                      '남은 총 투자 가능금액: ${usage['remaining_account_exposure_krw'] == null ? '제한 없음' : _krw.format(usage['remaining_account_exposure_krw'])}'),
                  Text(
                      '현재 최대 종목 투자금액: ${_krw.format(usage['largest_position_exposure_krw'])}'),
                ],
              ],
            ),
    );
  }
}
