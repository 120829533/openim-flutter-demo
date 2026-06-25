import 'package:get/get.dart';

/// 调试版推送控制器。
///
/// 当前项目调试阶段不启用 Firebase/FCM，避免引入 firebase_messaging、google-services
/// 等重型原生依赖，显著减少 Android 首次编译耗时。
enum PushType { none }

class PushController extends GetxService {
  PushType pushType = PushType.none;

  static void login(String alias, {void Function(String token)? onTokenRefresh}) {}

  static void logout() {}
}
