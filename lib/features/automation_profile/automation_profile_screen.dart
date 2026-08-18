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
      'enabled': false,
      'status': 'disabled',
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
        title: const Text('Automation Profiles'),
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
                const Text('Profiles describe search, sizing, and monitoring only. They do not change live safety flags.', style: TextStyle(color: Colors.white70)),
                const SizedBox(height: 12),
                for (final profile in _list?.profiles ?? const <AutomationStrategyProfile>[])
                  Card(
                    key: ValueKey('automation-profile-${profile.id}'),
                    child: ListTile(
                      title: Text(profile.name),
                      subtitle: Text('${profile.profileKey} · ${profile.status} · max positions ${profile.maxOpenPositions}'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => _edit(profile),
                    ),
                  ),
                const SizedBox(height: 16),
                _editor(context),
              ],
            ),
    );
  }

  Widget _editor(BuildContext context) {
    return Card(
      key: const ValueKey('automation-profile-editor'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_selected == null ? 'Create profile' : 'Edit profile', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 12),
            TextField(key: const ValueKey('automation-profile-key'), controller: _keyController, decoration: const InputDecoration(labelText: 'Profile key')),
            TextField(key: const ValueKey('automation-profile-name'), controller: _nameController, decoration: const InputDecoration(labelText: 'Name')),
            Row(children: [
              Expanded(child: TextField(controller: _startController, decoration: const InputDecoration(labelText: 'Start date'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _endController, decoration: const InputDecoration(labelText: 'End date'))),
            ]),
            TextField(controller: _maxEntriesController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Max new entries per day')),
            TextField(controller: _timesController, decoration: const InputDecoration(labelText: 'Analysis times (HH:mm,...)')),
            Row(children: [
              Expanded(child: TextField(controller: _watchlistController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Watchlist size'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(key: const ValueKey('automation-profile-max-positions'), controller: _maxPositionsController, keyboardType: TextInputType.number, onChanged: (_) => setState(() {}), decoration: const InputDecoration(labelText: 'Max open positions'))),
            ]),
            DropdownButtonFormField<String>(initialValue: _sizingMode, items: const [
              DropdownMenuItem(value: 'equity_pct', child: Text('Equity percentage')),
              DropdownMenuItem(value: 'fixed_budget', child: Text('Fixed budget')),
            ], onChanged: (value) => setState(() => _sizingMode = value ?? 'equity_pct'), decoration: const InputDecoration(labelText: 'Sizing mode')),
            Row(children: [
              Expanded(child: TextField(controller: _targetPctController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Target position %'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _maxOrderController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Max order KRW'))),
            ]),
            TextField(controller: _fixedBudgetController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Fixed budget KRW (when selected)')),
            Row(children: [
              Expanded(child: TextField(controller: _stopLossController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Stop-loss %'))),
              const SizedBox(width: 8),
              Expanded(child: TextField(controller: _takeProfitController, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'Take-profit %'))),
            ]),
            if ((int.tryParse(_maxPositionsController.text) ?? 1) > 1)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text('Multi-position live execution is not supported yet; the PR109 portfolio engine is required.', key: ValueKey('automation-profile-multi-position-warning'), style: TextStyle(color: Colors.orangeAccent)),
              ),
            const SizedBox(height: 12),
            Wrap(spacing: 8, children: [
              FilledButton(key: const ValueKey('automation-profile-save'), onPressed: _busy ? null : _save, child: const Text('Save')),
              OutlinedButton(key: const ValueKey('automation-profile-validate'), onPressed: _selected == null ? null : _validate, child: const Text('Validate')),
            ]),
            const SizedBox(height: 14),
            TextField(key: const ValueKey('automation-profile-search'), decoration: const InputDecoration(labelText: 'Search symbols (read-only)'), onSubmitted: (query) async {
              if (query.trim().isEmpty) return;
              final results = await widget.apiClient.searchSymbols(query, market: 'KR');
              if (!mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(results.map((item) => '${item['name']} (${item['symbol']})').join(', '))));
            }),
            const SizedBox(height: 6),
            const Text('Favorites, manual watchlist, and auto universe remain separate profile settings.', style: TextStyle(color: Colors.white54)),
          ],
        ),
      ),
    );
  }
}
