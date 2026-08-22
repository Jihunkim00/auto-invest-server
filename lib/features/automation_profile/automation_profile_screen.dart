import 'package:flutter/material.dart';

import '../../core/network/api_client.dart';
import '../../models/automation_strategy_profile.dart';

class AutomationProfileScreen extends StatefulWidget {
  const AutomationProfileScreen({super.key, required this.apiClient});

  final ApiClient apiClient;

  @override
  State<AutomationProfileScreen> createState() => _AutomationProfileScreenState();
}

class _AutomationProfileScreenState extends State<AutomationProfileScreen> {
  AutomationStrategyProfileList? _list;
  AutomationStrategyProfile? _selected;
  String? _error;
  bool _busy = false;
  final _keyController = TextEditingController();
  final _nameController = TextEditingController();
  final _startController = TextEditingController(text: '2026-08-17');
  final _endController = TextEditingController(text: '2026-09-18');
  final _timesController = TextEditingController(text: '09:10,11:30,13:30');
  final _watchlistController = TextEditingController(text: '50');
  final _maxPositionsController = TextEditingController(text: '1');
  final _targetPctController = TextEditingController(text: '10');
  final _fixedBudgetController = TextEditingController(text: '500000');
  final _maxOrderController = TextEditingController(text: '500000');
  final _stopLossController = TextEditingController(text: '2');
  final _takeProfitController = TextEditingController(text: '3');
  final _maxEntriesController = TextEditingController(text: '1');
  String _sizingMode = 'equity_pct';

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final controller in [
      _keyController,
      _nameController,
      _startController,
      _endController,
      _timesController,
      _watchlistController,
      _maxPositionsController,
      _targetPctController,
      _fixedBudgetController,
      _maxOrderController,
      _stopLossController,
      _takeProfitController,
      _maxEntriesController,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _busy = true);
    try {
      final result = await widget.apiClient.fetchAutomationProfiles();
      if (!mounted) return;
      setState(() {
        _list = result;
        _error = null;
        _busy = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString();
        _busy = false;
      });
    }
  }

  void _newProfile() {
    setState(() {
      _selected = null;
      _keyController.text = '';
      _nameController.text = '';
      _sizingMode = 'equity_pct';
      _maxPositionsController.text = '1';
    });
  }

  void _edit(AutomationStrategyProfile profile) {
    setState(() {
      _selected = profile;
      _keyController.text = profile.profileKey;
      _nameController.text = profile.name;
      _startController.text = '${profile.operation['start_date'] ?? '2026-08-17'}';
      _endController.text = '${profile.operation['end_date'] ?? '2026-09-18'}';
      final times = profile.entry['analysis_times'];
      _timesController.text = times is List ? times.join(',') : '09:10,11:30,13:30';
      _watchlistController.text = '${profile.universe['watchlist_size'] ?? 50}';
      _maxPositionsController.text = '${profile.maxOpenPositions}';
      _targetPctController.text = '${profile.capital['target_position_pct'] ?? 10}';
      _fixedBudgetController.text = '${profile.capital['fixed_budget'] ?? 500000}';
      _maxOrderController.text = '${profile.capital['max_order_notional_krw'] ?? 500000}';
      _stopLossController.text = '${profile.exit['stop_loss_pct'] ?? 2}';
      _takeProfitController.text = '${profile.exit['take_profit_pct'] ?? 3}';
      _maxEntriesController.text = '${profile.entry['max_new_entries_per_day'] ?? 1}';
      _sizingMode = '${profile.capital['sizing_mode'] ?? 'equity_pct'}';
    });
  }

  Map<String, dynamic> _body() {
    final target = double.tryParse(_targetPctController.text) ?? 10;
    return {
      'profile_key': _keyController.text.trim(),
      'name': _nameController.text.trim(),
      'provider': 'kis',
      'market': 'KR',
      'enabled': _selected?.status == 'active',
      'status': _selected?.status == 'active' ? 'active' : 'disabled',
      'capital': {
        'sizing_mode': _sizingMode,
        'target_position_pct': target,
        'max_position_pct': target,
        'max_total_exposure_pct': target,
        'max_order_notional_krw': double.tryParse(_maxOrderController.text) ?? 500000,
        'fixed_budget': double.tryParse(_fixedBudgetController.text) ?? 500000,
        'cash_only': true,
      },
      'universe': {
        'universe_mode': 'auto',
        'watchlist_size': int.tryParse(_watchlistController.text) ?? 50,
        'min_price_krw': 5000,
        'max_price_krw': 500000,
        'include_kospi': true,
        'include_kosdaq': true,
        'exclude_preferred': true,
        'exclude_etf': true,
        'exclude_etn': true,
        'exclude_spac': true,
      },
      'entry': {
        'analysis_times': _timesController.text
            .split(',')
            .map((value) => value.trim())
            .where((value) => value.isNotEmpty)
            .toList(),
        'no_new_entry_after': '14:00',
        'max_new_entries_per_day': int.tryParse(_maxEntriesController.text) ?? 1,
        'max_entries_per_scan': 1,
        'min_final_score': 65,
        'gate_level': 2,
      },
      'monitoring': {'interval_seconds': 60},
      'exit': {
        'stop_loss_enabled': true,
        'stop_loss_pct': double.tryParse(_stopLossController.text) ?? 2,
        'take_profit_enabled': true,
        'take_profit_pct': double.tryParse(_takeProfitController.text) ?? 3,
      },
      'operation': {
        'start_date': _startController.text.trim(),
        'end_date': _endController.text.trim(),
        'weekdays_only': true,
        'auto_start': false,
        'end_policy': 'manage_until_exit',
      },
      'max_open_positions': int.tryParse(_maxPositionsController.text) ?? 1,
    };
  }

  Future<void> _save() async {
    setState(() => _busy = true);
    try {
      final body = _body();
      if (_selected == null) {
        await widget.apiClient.createAutomationProfile(body);
      } else {
        await widget.apiClient.updateAutomationProfile(_selected!.id, body);
      }
      await _load();
      if (mounted) setState(() => _error = null);
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _activate(AutomationStrategyProfile profile) async {
    setState(() => _busy = true);
    try {
      await widget.apiClient.activateAutomationProfile(profile.id);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('운용 프로필을 활성화했습니다. 실거래 권한은 별도 안전 게이트입니다.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _pause(AutomationStrategyProfile profile) async {
    setState(() => _busy = true);
    try {
      await widget.apiClient.pauseAutomationProfile(profile.id);
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('운용 프로필을 일시정지했습니다.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _validate() async {
    if (_selected == null) {
      setState(() => _error = 'Save the profile before validating it.');
      return;
    }
    try {
      final result = await widget.apiClient.validateAutomationProfile(_selected!.id);
      if (mounted) {
        setState(() => _error = result['valid'] == true ? null : '${result['errors']}');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result['valid'] == true ? 'Profile is valid.' : 'Profile validation failed.')),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('자동화 프로필'),
        actions: [
          IconButton(key: const ValueKey('automation-profile-create'), onPressed: _newProfile, icon: const Icon(Icons.add)),
        ],
      ),
      body: _busy && _list == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (_error != null) Text(_error!, key: const ValueKey('automation-profile-error'), style: const TextStyle(color: Colors.orangeAccent)),
                const Text('프로필은 종목 탐색·자금 배분·분석·모니터링 정책을 정의합니다. 실거래 안전 플래그와 주문 권한은 별도로 유지됩니다.', style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 12),
                for (final profile in _list?.profiles ?? const <AutomationStrategyProfile>[])
                  Card(
                    key: ValueKey('automation-profile-${profile.id}'),
                    child: ListTile(
                      title: Text(profile.name),
                      subtitle: Text('${profile.profileKey} · ${_statusLabel(profile.status)} · 최대 포지션 ${profile.maxOpenPositions}'),
                      trailing: Wrap(spacing: 0, children: [
                        IconButton(
                          key: ValueKey('automation-profile-activate-${profile.id}'),
                          tooltip: '활성 프로필로 설정',
                          onPressed: _busy || profile.status == 'active' ? null : () => _activate(profile),
                          icon: const Icon(Icons.play_arrow_outlined),
                        ),
                        IconButton(
                          key: ValueKey('automation-profile-pause-${profile.id}'),
                          tooltip: '프로필 일시정지',
                          onPressed: _busy || profile.status != 'active' ? null : () => _pause(profile),
                          icon: const Icon(Icons.pause_outlined),
                        ),
                        const Icon(Icons.chevron_right),
                      ]),
                      onTap: () => _edit(profile),
                    ),
                  ),
                const SizedBox(height: 16),
                _editor(context),
              ],
            ),
    );
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'active':
        return '활성';
      case 'paused':
        return '일시정지';
      case 'archived':
        return '보관';
      default:
        return '비활성';
    }
  }

  Widget _editor(BuildContext context) {
    return Card(
      key: const ValueKey('automation-profile-editor'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_selected == null ? '프로필 생성' : '프로필 편집', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            TextField(key: const ValueKey('automation-profile-key'), controller: _keyController, readOnly: _selected?.status == 'active', decoration: const InputDecoration(labelText: '프로필 키 (내부 식별자)')),
            TextField(key: const ValueKey('automation-profile-name'), controller: _nameController, decoration: const InputDecoration(labelText: '프로필 이름')),
            Row(children: [
              Expanded(child: TextField(controller: _startController, decoration: const InputDecoration(labelText: '시작일'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _endController, decoration: const InputDecoration(labelText: '종료일'))),
            ]),
            TextField(controller: _maxEntriesController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '일일 신규 진입 한도')),
            TextField(controller: _timesController, decoration: const InputDecoration(labelText: '분석 시각 (HH:mm,...)')),
            Row(children: [
              Expanded(child: TextField(controller: _watchlistController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '관심종목 수'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(key: const ValueKey('automation-profile-max-positions'), controller: _maxPositionsController, keyboardType: TextInputType.number, onChanged: (_) => setState(() {}), decoration: const InputDecoration(labelText: '최대 보유 포지션'))),
            ]),
            DropdownButtonFormField<String>(initialValue: _sizingMode, items: const [
              DropdownMenuItem(value: 'equity_pct', child: Text('자산 비율')),
              DropdownMenuItem(value: 'fixed_budget', child: Text('고정 예산')),
            ], onChanged: (value) => setState(() => _sizingMode = value ?? 'equity_pct'), decoration: const InputDecoration(labelText: '자금 배분 방식')),
            Row(children: [
              Expanded(child: TextField(controller: _targetPctController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '목표 포지션 비율'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _maxOrderController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '최대 주문 금액 (원)'))),
            ]),
            TextField(controller: _fixedBudgetController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '고정 예산 (원)')),
            Row(children: [
              Expanded(child: TextField(controller: _stopLossController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '손절 비율'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _takeProfitController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: '익절 비율'))),
            ]),
            if ((int.tryParse(_maxPositionsController.text) ?? 1) > 1)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text('다중 포지션 실거래는 아직 지원되지 않습니다. PR109 포트폴리오 엔진이 필요합니다.', key: ValueKey('automation-profile-multi-position-warning'), style: TextStyle(color: Colors.orangeAccent)),
              ),
            const SizedBox(height: 12),
            Wrap(spacing: 8, children: [
              FilledButton(key: const ValueKey('automation-profile-save'), onPressed: _busy ? null : _save, child: const Text('저장')),
              OutlinedButton(key: const ValueKey('automation-profile-validate'), onPressed: _selected == null ? null : _validate, child: const Text('검증')),
              if (_selected != null && _selected!.status != 'active')
                OutlinedButton(key: const ValueKey('automation-profile-start'), onPressed: _busy ? null : () => _activate(_selected!), child: const Text('운용 시작')),
              if (_selected != null && _selected!.status == 'active')
                OutlinedButton(key: const ValueKey('automation-profile-stop'), onPressed: _busy ? null : () => _pause(_selected!), child: const Text('운용 정지')),
            ]),
            const SizedBox(height: 14),
            TextField(key: const ValueKey('automation-profile-search'), decoration: const InputDecoration(labelText: '종목 검색 (읽기 전용)'), onSubmitted: (query) async {
              if (query.trim().isEmpty) return;
              final results = await widget.apiClient.searchSymbols(query, market: 'KR');
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(results.map((item) => '${item['name']} (${item['symbol']})').join(', '))));
            }),
            const SizedBox(height: 6),
            const Text('즐겨찾기·수동 관심종목·자동 유니버스는 프로필별로 별도 관리됩니다.', style: TextStyle(color: Colors.white54)),
          ],
        ),
      ),
    );
  }
}
