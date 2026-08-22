import 'package:shared_preferences/shared_preferences.dart';

class ProviderPreferenceStore {
  const ProviderPreferenceStore();

  static const key = 'auto_invest.selected_provider';

  Future<String?> read() async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(key);
  }

  Future<void> write(String provider) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(key, provider);
  }
}
