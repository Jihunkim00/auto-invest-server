import 'package:http/http.dart' as http;

import 'default_http_client_stub.dart'
    if (dart.library.js_interop) 'default_http_client_web.dart';

http.Client createDefaultHttpClient() => createPlatformHttpClient();
