import 'dart:async';

import 'package:flutter/material.dart';
import 'package:openim_common/openim_common.dart';

import 'app.dart';

void main() {
  runZonedGuarded(() {
    FlutterError.onError = (FlutterErrorDetails details) {
      // 打印到 logcat 方便调试
      debugPrint('========== FlutterError ==========');
      debugPrint('Exception: ${details.exception}');
      debugPrint('Stack: ${details.stack}');
      debugPrint('Library: ${details.library}');
      debugPrint('Context: ${details.context}');
      debugPrint('==================================');
      FlutterError.presentError(details);
      Logger.print('FlutterError: ${details.exception.toString()}, ${details.stack.toString()}');
    };

    Config.init(() => runApp(const ChatApp()));
  }, (error, stackTrace) {
    Logger.print('FlutterError: ${error.toString()}, ${stackTrace.toString()}', onlyConsole: true);
  });
}
