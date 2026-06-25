#!/bin/bash
set -e

echo "=== 1. 编译 Flutter APK (debug) ==="
cd /home/bing/openim-flutter-demo/client
flutter build apk --debug

echo ""
echo "=== 2. 杀掉 APK 进程 ==="
adb shell am force-stop io.openim.flutter.demo || true

echo ""
echo "=== 3. 卸载旧版 APK ==="
adb uninstall io.openim.flutter.demo || true

echo ""
echo "=== 4. 安装最新 APK ==="
adb install -r "/home/bing/openim-flutter-demo/client/build/app/outputs/flutter-apk/app-debug.apk"

echo ""
echo "=== 全部完成 ==="
