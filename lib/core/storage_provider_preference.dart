import 'package:shared_preferences/shared_preferences.dart';

class ProviderPreferenceStore {
  const ProviderPreferenceStore();

  static const key = 'auto_invest.selected_provider';

  String _userKey(String userScope) => '$key.user.$userScope';

  Future<String?> read() async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(key);
  }

  Future<void> write(String provider) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(key, provider);
  }

  Future<String?> readForUser(String userScope) async {
    final preferences = await SharedPreferences.getInstance();
    return preferences.getString(_userKey(userScope));
  }

  Future<void> writeForUser(String userScope, String provider) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(_userKey(userScope), provider);
  }
}
