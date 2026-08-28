import 'package:flutter/material.dart';

import '../../core/i18n/app_language.dart';
import '../../core/network/api_client.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/section_card.dart';
import '../../models/automation_strategy_profile.dart';

class AutomationProfileScreen extends StatefulWidget {
  const AutomationProfileScreen({
    super.key,
    required this.apiClient,
    this.appLanguage = AppLanguage.korean,
  });

  final ApiClient apiClient;
  final AppLanguage appLanguage;

  @override
  State<AutomationProfileScreen> createState() =>
      _AutomationProfileScreenState();
}

class _AutomationProfileScreenState extends State<AutomationProfileScreen> {
  static const _defaultStartDate = '2026-08-17';
  static const _defaultEndDate = '2026-09-18';

  AutomationStrategyProfileList? _list;
  AutomationStrategyProfile? _selected;
  String? _error;
  bool _busy = false;
  final _nameController = TextEditingController();
  final _startController = TextEditingController(text: _defaultStartDate);
  final _endController = TextEditingController(text: _defaultEndDate);
  List<String> _analysisTimes = <String>['09:10', '11:30', '13:30'];
  final _watchlistController = TextEditingController(text: '50');
  final _maxPositionsController = TextEditingController(text: '1');
  final _targetPctController = TextEditingController(text: '10');
  final _fixedBudgetController = TextEditingController(text: '500000');
  final _maxOrderController = TextEditingController(text: '500000');
  final _stopLossController = TextEditingController(text: '2');
  final _takeProfitController = TextEditingController(text: '3');
  final _maxEntriesController = TextEditingController(text: '1');
  String _sizingMode = 'equity_pct';
  double _maxPositionPct = 12;
  double _maxTotalExposurePct = 30;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final controller in [
      _nameController,
      _startController,
      _endController,
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
      _nameController.text = '';
      _startController.text = _defaultStartDate;
      _endController.text = _defaultEndDate;
      _sizingMode = 'equity_pct';
      _maxPositionsController.text = '1';
      _analysisTimes = <String>['09:10', '11:30', '13:30'];
      _targetPctController.text = '10';
      _fixedBudgetController.text = '500000';
      _maxOrderController.text = '500000';
      _maxPositionPct = 12;
      _maxTotalExposurePct = 30;
    });
  }

  void _edit(AutomationStrategyProfile profile) {
    setState(() {
      _selected = profile;
      _nameController.text = profile.name;
      _startController.text =
          '${profile.operation['start_date'] ?? '2026-08-17'}';
      _endController.text = '${profile.operation['end_date'] ?? '2026-09-18'}';
      final times = profile.entry['analysis_times'];
      _analysisTimes = times is List
          ? times.map((value) => value.toString()).toSet().toList()
          : <String>['09:10', '11:30', '13:30'];
      _analysisTimes.sort();
      _watchlistController.text = '${profile.universe['watchlist_size'] ?? 50}';
      _maxPositionsController.text = '${profile.maxOpenPositions}';
      _targetPctController.text =
          '${profile.capital['target_position_pct'] ?? 10}';
      _fixedBudgetController.text =
          '${profile.capital['fixed_budget'] ?? 500000}';
      _maxOrderController.text =
          '${profile.capital['max_order_notional_krw'] ?? 500000}';
      _stopLossController.text = '${profile.exit['stop_loss_pct'] ?? 2}';
      _takeProfitController.text = '${profile.exit['take_profit_pct'] ?? 3}';
      _maxEntriesController.text =
          '${profile.entry['max_new_entries_per_day'] ?? 1}';
      _sizingMode = profile.capital['sizing_mode'] == 'fixed_budget'
          ? 'fixed_budget'
          : 'equity_pct';
      _maxPositionPct = _asDouble(profile.capital['max_position_pct'], 12);
      _maxTotalExposurePct =
          _asDouble(profile.capital['max_total_exposure_pct'], 30);
    });
  }

  Future<void> _addAnalysisTime() async {
    final seed = _analysisTimes.isEmpty
        ? const TimeOfDay(hour: 9, minute: 10)
        : _timeOfDayFromValue(_analysisTimes.last) ??
            const TimeOfDay(hour: 9, minute: 10);
    final picked = await showTimePicker(context: context, initialTime: seed);
    if (!mounted || picked == null) return;
    final value = _formatTime(picked);
    if (_analysisTimes.contains(value)) {
      setState(() => _error = "분석 시각은 중복될 수 없습니다.");
      return;
    }
    setState(() {
      _analysisTimes = [..._analysisTimes, value]..sort();
      _error = null;
    });
  }

  Future<void> _pickDate({required bool start}) async {
    final controller = start ? _startController : _endController;
    final current = _parseDate(controller.text) ??
        _parseDate(start ? _defaultStartDate : _defaultEndDate)!;
    final picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
      locale: widget.appLanguage == AppLanguage.korean
          ? const Locale('ko', 'KR')
          : const Locale('en', 'US'),
      helpText: start ? '시작일 선택' : '종료일 선택',
    );
    if (!mounted || picked == null) return;
    setState(() {
      controller.text = _formatDate(picked);
      _error = _dateRangeError();
    });
  }

  DateTime? _parseDate(String value) {
    final text = value.trim();
    final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(text);
    if (match == null) return null;
    final date = DateTime.tryParse(text);
    if (date == null ||
        date.year != int.parse(match.group(1)!) ||
        date.month != int.parse(match.group(2)!) ||
        date.day != int.parse(match.group(3)!)) {
      return null;
    }
    return date;
  }

  String _formatDate(DateTime value) =>
      '${value.year.toString().padLeft(4, '0')}-'
      '${value.month.toString().padLeft(2, '0')}-'
      '${value.day.toString().padLeft(2, '0')}';

  String? _dateRangeError() {
    final start = _parseDate(_startController.text);
    final end = _parseDate(_endController.text);
    if (start == null || end == null) {
      return '시작일과 종료일은 yyyy-MM-dd 형식이어야 합니다.';
    }
    if (start.isAfter(end)) return '시작일은 종료일보다 늦을 수 없습니다.';
    return null;
  }

  void _removeAnalysisTime(String value) {
    if (_analysisTimes.length <= 1) {
      setState(() => _error = "분석 시각은 최소 1개가 필요합니다.");
      return;
    }
    setState(() => _analysisTimes =
        _analysisTimes.where((item) => item != value).toList());
  }

  TimeOfDay? _timeOfDayFromValue(String value) {
    final parts = value.split(":");
    if (parts.length != 2) return null;
    final hour = int.tryParse(parts[0]);
    final minute = int.tryParse(parts[1]);
    if (hour == null ||
        minute == null ||
        hour < 0 ||
        hour > 23 ||
        minute < 0 ||
        minute > 59) {
      return null;
    }
    return TimeOfDay(hour: hour, minute: minute);
  }

  String _formatTime(TimeOfDay value) =>
      value.hour.toString().padLeft(2, "0") +
      ":" +
      value.minute.toString().padLeft(2, "0");

  String? _validateEditor() {
    final dateError = _dateRangeError();
    if (dateError != null) return dateError;
    if (_analysisTimes.isEmpty) return "분석 시각은 최소 1개가 필요합니다.";
    final seen = <String>{};
    for (final value in _analysisTimes) {
      final time = _timeOfDayFromValue(value);
      if (time == null) return "분석 시각은 HH:mm 형식이어야 합니다.";
      final minutes = time.hour * 60 + time.minute;
      if (minutes < 9 * 60 || minutes > 15 * 60 + 30) {
        return "분석 시각은 KST 09:00~15:30 범위여야 합니다.";
      }
      if (minutes >= 14 * 60) return "분석 시각은 신규 진입 cutoff 14:00 전이어야 합니다.";
      if (!seen.add(value)) return "분석 시각은 중복될 수 없습니다.";
    }
    final takeProfit = double.tryParse(_takeProfitController.text);
    if (takeProfit == null || takeProfit < 1 || takeProfit > 15) {
      return "Take Profit은 1%~15% 범위여야 합니다.";
    }
    return null;
  }

  double _asDouble(Object? value, double fallback) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '') ?? fallback;
  }

  Map<String, dynamic> _body() {
    final target = double.tryParse(_targetPctController.text) ?? 10;
    return {
      // The backend assigns and preserves profile identity; normal UI omits it.
      'name': _nameController.text.trim(),
      'provider': 'kis',
      'market': 'KR',
      'enabled': _selected?.status == 'active',
      'status': _selected?.status == 'active' ? 'active' : 'disabled',
      'capital': {
        'sizing_mode': _sizingMode,
        'target_position_pct': target,
        'max_position_pct': _maxPositionPct,
        'max_total_exposure_pct': _maxTotalExposurePct,
        'max_order_notional_krw':
            double.tryParse(_maxOrderController.text) ?? 500000,
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
        'analysis_times': List<String>.from(_analysisTimes),
        'no_new_entry_after': '14:00',
        'max_new_entries_per_day':
            int.tryParse(_maxEntriesController.text) ?? 1,
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
        'timezone': 'Asia/Seoul',
        'weekdays_only': true,
        'auto_start': false,
        'end_policy': 'manage_until_exit',
      },
      'max_open_positions': int.tryParse(_maxPositionsController.text) ?? 1,
    };
  }

  Future<void> _save() async {
    final validation = _validateEditor();
    if (validation != null) {
      setState(() => _error = validation);
      return;
    }
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
        const SnackBar(
            content: Text('프로필을 활성화했습니다. 주문 권한과 안전 게이트는 별도로 유지됩니다.')),
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
        const SnackBar(content: Text('프로필을 일시정지했습니다.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _validate() async {
    if (_selected == null) {
      setState(() => _error = '검증하려면 먼저 프로필을 저장하세요.');
      return;
    }
    try {
      final result =
          await widget.apiClient.validateAutomationProfile(_selected!.id);
      if (mounted) {
        setState(() =>
            _error = result['valid'] == true ? null : '${result['errors']}');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
              content: Text(
                  result['valid'] == true ? '프로필이 유효합니다.' : '프로필 검증에 실패했습니다.')),
        );
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    }
  }

  bool _isSelected(AutomationStrategyProfile profile) =>
      _list?.selectedProfile?.id == profile.id;

  bool _isArmed(AutomationStrategyProfile profile) {
    if (!_isSelected(profile)) return false;
    final status = _list?.selectedProfileStatus;
    return status == "scheduled" || status == "active";
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('자동화 프로필'),
        actions: [
          IconButton(
            key: const ValueKey('automation-profile-create'),
            onPressed: _newProfile,
            tooltip: '새 프로필',
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      body: _busy && _list == null
          ? const Center(child: CircularProgressIndicator())
          : Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    if (_error != null)
                      Text(
                        _error!,
                        key: const ValueKey('automation-profile-error'),
                        style: const TextStyle(color: Colors.orangeAccent),
                      ),
                    const Text(
                      '자동화 프로필은 종목 탐색, 자금 배분, 분석, 모니터링을 정의합니다. 주문 권한과 기존 안전 게이트는 별도로 유지됩니다.',
                      style: TextStyle(color: Colors.white70),
                    ),
                    const SizedBox(height: 12),
                    for (final profile in _list?.profiles ??
                        const <AutomationStrategyProfile>[])
                      SectionCard(
                        key: ValueKey('automation-profile-${profile.id}'),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 4),
                        child: ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(profile.name),
                          subtitle: Text(
                              '${profile.provider.toLowerCase() == 'kis' ? '한국투자증권' : '알파카'} / ${profile.market.toUpperCase()} · ${_statusLabel(profile.status)} · 최대 보유 ${profile.maxOpenPositions}종목'),
                          trailing: Wrap(
                            spacing: 0,
                            children: [
                              IconButton(
                                key: ValueKey(
                                    'automation-profile-activate-${profile.id}'),
                                tooltip: '프로필 활성화',
                                onPressed: _busy ||
                                        profile.status == 'active' ||
                                        _isArmed(profile)
                                    ? null
                                    : () => _activate(profile),
                                icon: const Icon(Icons.play_arrow_outlined),
                              ),
                              IconButton(
                                key: ValueKey(
                                    'automation-profile-pause-${profile.id}'),
                                tooltip: '프로필 일시정지',
                                onPressed: _busy ||
                                        (!_isSelected(profile) &&
                                            profile.status != 'active')
                                    ? null
                                    : () => _pause(profile),
                                icon: const Icon(Icons.pause_outlined),
                              ),
                              const Icon(Icons.chevron_right),
                            ],
                          ),
                          onTap: () => _edit(profile),
                        ),
                      ),
                    const SizedBox(height: 16),
                    _editor(context),
                  ],
                ),
              ),
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
    return SectionCard(
      key: const ValueKey('automation-profile-editor'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_selected == null ? '프로필 생성' : '프로필 편집',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          const _FormSectionHeading(
            icon: Icons.tune_outlined,
            title: '기본 설정',
            topSpacing: 0,
          ),
          _LabeledField(
            label: '프로필 이름',
            field: TextField(
              key: const ValueKey('automation-profile-name'),
              controller: _nameController,
              decoration: const InputDecoration(),
            ),
          ),
          const SizedBox(height: 16),
          const ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(Icons.account_balance_outlined),
            title: Text('증권사 / 시장'),
            subtitle: Text('한국투자증권 · 국내주식'),
          ),
          const SizedBox(height: 12),
          _ProfileFieldRow(
            fields: [
              _LabeledField(
                label: '시작일',
                field: _DateField(
                  fieldKey: const ValueKey('automation-profile-start-date'),
                  controller: _startController,
                  onTap: () => _pickDate(start: true),
                ),
              ),
              _LabeledField(
                label: '종료일',
                field: _DateField(
                  fieldKey: const ValueKey('automation-profile-end-date'),
                  controller: _endController,
                  onTap: () => _pickDate(start: false),
                ),
              ),
            ],
          ),
          const _FormSectionHeading(
            icon: Icons.schedule_outlined,
            title: '실행 일정',
          ),
          _LabeledField(
            label: '일일 신규 진입 횟수',
            field: TextField(
              controller: _maxEntriesController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(),
            ),
          ),
          const SizedBox(height: 16),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '분석 시각 (KST)',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  OutlinedButton.icon(
                    key: const ValueKey("automation-profile-add-analysis-time"),
                    onPressed: _busy ? null : _addAnalysisTime,
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text("시간 추가"),
                  ),
                ],
              ),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final value in _analysisTimes)
                    InputChip(
                      label: Text(value),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 8),
                      labelPadding: const EdgeInsets.symmetric(horizontal: 6),
                      materialTapTargetSize: MaterialTapTargetSize.padded,
                      onDeleted: () => _removeAnalysisTime(value),
                    ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                "중복 금지 · 최소 1개 · 09:00~15:30 · 신규 진입 마감 14:00 전",
                style: TextStyle(color: Colors.white54, height: 1.4),
              ),
            ],
          ),
          const _FormSectionHeading(
            icon: Icons.search_outlined,
            title: '탐색 범위',
          ),
          _ProfileFieldRow(
            fields: [
              _LabeledField(
                label: '관심종목 수',
                field: TextField(
                  controller: _watchlistController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(),
                ),
              ),
              _LabeledField(
                label: '최대 보유 종목',
                field: TextField(
                  key: const ValueKey('automation-profile-max-positions'),
                  controller: _maxPositionsController,
                  keyboardType: TextInputType.number,
                  onChanged: (_) => setState(() {}),
                  decoration: const InputDecoration(),
                ),
              ),
            ],
          ),
          const _FormSectionHeading(
            icon: Icons.account_balance_wallet_outlined,
            title: '자금 관리',
          ),
          _LabeledField(
            label: '자금 배분 방식',
            field: DropdownButtonFormField<String>(
              key: ValueKey('automation-profile-sizing-mode-$_sizingMode'),
              initialValue: _sizingMode,
              items: const [
                DropdownMenuItem(
                    key: ValueKey('automation-profile-sizing-equity-pct'),
                    value: 'equity_pct',
                    child: Text('자산 비율')),
                DropdownMenuItem(
                    key: ValueKey('automation-profile-sizing-fixed-budget'),
                    value: 'fixed_budget',
                    child: Text('고정 예산')),
              ],
              onChanged: (value) => setState(() => _sizingMode =
                  value == 'fixed_budget' ? 'fixed_budget' : 'equity_pct'),
              decoration: const InputDecoration(),
            ),
          ),
          const SizedBox(height: 18),
          _ProfileFieldRow(
            fields: [
              _LabeledField(
                label: '목표 포지션 비율',
                helper: _sizingMode == 'fixed_budget'
                    ? '고정 예산 방식에서는 목표 자산 비율을 사용하지 않습니다.'
                    : null,
                helperKey: _sizingMode == 'fixed_budget'
                    ? const ValueKey('automation-profile-target-pct-helper')
                    : null,
                field: TextField(
                  key: const ValueKey('automation-profile-target-pct'),
                  enabled: _sizingMode == 'equity_pct',
                  controller: _targetPctController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(),
                ),
              ),
              _LabeledField(
                label: '최대 주문 금액 (원)',
                field: TextField(
                  key: const ValueKey('automation-profile-max-order'),
                  controller: _maxOrderController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(),
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          _LabeledField(
            label: '고정 예산 (원)',
            helper: _sizingMode == 'equity_pct'
                ? '자산 비율 방식에서는 고정 예산을 사용하지 않습니다.'
                : null,
            helperKey: _sizingMode == 'equity_pct'
                ? const ValueKey('automation-profile-fixed-budget-helper')
                : null,
            field: TextField(
              key: const ValueKey('automation-profile-fixed-budget'),
              enabled: _sizingMode == 'fixed_budget',
              controller: _fixedBudgetController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(),
            ),
          ),
          const _FormSectionHeading(
            icon: Icons.shield_outlined,
            title: '리스크 관리',
          ),
          _ProfileFieldRow(
            fields: [
              _LabeledField(
                label: '손절 비율',
                field: TextField(
                  controller: _stopLossController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(),
                ),
              ),
              _LabeledField(
                label: '익절 비율',
                field: TextField(
                  key: const ValueKey("automation-profile-take-profit"),
                  controller: _takeProfitController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(),
                ),
              ),
            ],
          ),
          if ((int.tryParse(_maxPositionsController.text) ?? 1) > 1)
            const Padding(
              padding: EdgeInsets.only(top: 12),
              child: Text(
                '다중 포지션 실행은 아직 지원되지 않습니다. PR109 포트폴리오 엔진이 필요합니다.',
                key: ValueKey('automation-profile-multi-position-warning'),
                style: TextStyle(color: Colors.orangeAccent),
              ),
            ),
          const SizedBox(height: 20),
          Wrap(
            spacing: 8,
            children: [
              FilledButton(
                  key: const ValueKey('automation-profile-save'),
                  onPressed: _busy ? null : _save,
                  child: const Text('저장')),
              OutlinedButton(
                  key: const ValueKey('automation-profile-validate'),
                  onPressed: _selected == null ? null : _validate,
                  child: const Text('검증')),
              if (_selected != null && _selected!.status != 'active')
                OutlinedButton(
                    key: const ValueKey('automation-profile-start'),
                    onPressed: _busy ? null : () => _activate(_selected!),
                    child: const Text('사용 시작')),
              if (_selected != null && _selected!.status == 'active')
                OutlinedButton(
                    key: const ValueKey('automation-profile-stop'),
                    onPressed: _busy ? null : () => _pause(_selected!),
                    child: const Text('사용 중지')),
            ],
          ),
          const SizedBox(height: 24),
          _LabeledField(
            label: '종목 검색 (조회 전용)',
            field: TextField(
              key: const ValueKey('automation-profile-search'),
              decoration: const InputDecoration(hintText: '종목명 또는 종목코드'),
              onSubmitted: (query) async {
                if (query.trim().isEmpty) return;
                final results =
                    await widget.apiClient.searchSymbols(query, market: 'KR');
                if (!mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                      content: Text(results
                          .map((item) => '${item['name']} (${item['symbol']})')
                          .join(', '))),
                );
              },
            ),
          ),
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              '종목 검색과 수동 관심종목은 프로필별로 관리되며 주문 제출 권한과는 분리됩니다.',
              style: TextStyle(color: Colors.white54, height: 1.4),
            ),
          ),
        ],
      ),
    );
  }
}

class _FormSectionHeading extends StatelessWidget {
  const _FormSectionHeading({
    required this.icon,
    required this.title,
    this.topSpacing = 24,
  });

  final IconData icon;
  final String title;
  final double topSpacing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(top: topSpacing, bottom: 12),
      child: Row(
        children: [
          Icon(icon, size: 18, color: AppTheme.primaryAccent),
          const SizedBox(width: 8),
          Text(title,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    fontSize: 16,
                  )),
        ],
      ),
    );
  }
}

class _LabeledField extends StatelessWidget {
  const _LabeledField({
    required this.label,
    required this.field,
    this.helper,
    this.helperKey,
  });

  final String label;
  final Widget field;
  final String? helper;
  final Key? helperKey;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.labelLarge,
        ),
        const SizedBox(height: 6),
        field,
        if (helper != null)
          Padding(
            padding: const EdgeInsets.only(top: 7),
            child: Text(
              helper!,
              key: helperKey,
              style: const TextStyle(color: Colors.white54, height: 1.4),
            ),
          ),
      ],
    );
  }
}

class _ProfileFieldRow extends StatelessWidget {
  const _ProfileFieldRow({required this.fields});

  final List<Widget> fields;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 640 || fields.length < 2) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var index = 0; index < fields.length; index++) ...[
                if (index > 0) const SizedBox(height: 16),
                fields[index],
              ],
            ],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var index = 0; index < fields.length; index++) ...[
              if (index > 0) const SizedBox(width: 16),
              Expanded(child: fields[index]),
            ],
          ],
        );
      },
    );
  }
}

class _DateField extends StatelessWidget {
  const _DateField({
    required this.fieldKey,
    required this.controller,
    required this.onTap,
  });

  final Key fieldKey;
  final TextEditingController controller;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return TextField(
      key: fieldKey,
      controller: controller,
      readOnly: true,
      onTap: onTap,
      decoration: InputDecoration(
        hintText: 'yyyy-MM-dd',
        suffixIcon: const Icon(Icons.calendar_month_outlined),
        suffixIconConstraints: const BoxConstraints(
          minWidth: 48,
          minHeight: 48,
        ),
      ),
    );
  }
}
