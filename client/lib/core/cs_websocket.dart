import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:openim_common/openim_common.dart';

/// CS WebSocket 服务
///
/// 客服客户端（cs_agent_001）通过此 WebSocket 连接 Java 后端，
/// 实时接收网页端访客发来的消息，实现访客 ↔ 客服双向即时通信。
///
/// 连接目标：wss://yunnaguanjian.com:8089/ws/chat?token=<jwt_token>
class CsWebSocketService {
  static final CsWebSocketService _instance = CsWebSocketService._();
  factory CsWebSocketService() => _instance;
  CsWebSocketService._();

  WebSocket? _ws;
  Timer? _heartbeatTimer;
  Timer? _reconnectTimer;

  bool _connected = false;
  bool get isConnected => _connected;
  bool _disposed = false;

  String? _token;
  String? _userId;

  /// 收到新消息时触发 (conversationId, senderId, content)
  final _onMessageController = StreamController<CsMessageData>.broadcast();
  Stream<CsMessageData> get onMessage => _onMessageController.stream;

  /// 连接状态变化
  final _onConnectionChanged = StreamController<bool>.broadcast();
  Stream<bool> get onConnectionChanged => _onConnectionChanged.stream;

  /// 初始化并连接
  void init(String token, String userId) {
    if (_disposed) return;
    _token = token;
    _userId = userId;
    _connect();
  }

  void _connect() {
    if (_disposed || _token == null) return;

    _cleanup();

    try {
      final wsUrl = Uri.parse('${Config.imWsUrl.replaceAll('/ws', '')}/ws/chat?token=$_token');
      Logger.print('[CS WS] 连接中... $wsUrl');

      WebSocket.connect(wsUrl.toString()).then((ws) {
        if (_disposed) {
          ws.close();
          return;
        }

        _ws = ws;
        Logger.print('[CS WS] 已连接');

        // 发送 login 消息
        ws.add(jsonEncode({
          'type': 'login',
          'data': {'token': _token}
        }));

        // 启动心跳
        _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
          if (_ws != null && _ws!.readyState == WebSocket.open) {
            _ws!.add(jsonEncode({'type': 'heartbeat'}));
          }
        });

        ws.listen(
          _onData,
          onError: (error) {
            Logger.print('[CS WS] 错误: $error');
          },
          onDone: () {
            Logger.print('[CS WS] 连接关闭');
            _setConnected(false);
            _scheduleReconnect();
          },
          cancelOnError: false,
        );

        _setConnected(true);
      }).catchError((e) {
        Logger.print('[CS WS] 连接失败: $e');
        _setConnected(false);
        _scheduleReconnect();
      });
    } catch (e) {
      Logger.print('[CS WS] 创建连接异常: $e');
      _setConnected(false);
      _scheduleReconnect();
    }
  }

  void _onData(dynamic data) {
    try {
      final msg = jsonDecode(data as String);
      final type = msg['type'] as String?;
      Logger.print('[CS WS] 收到: $type');

      switch (type) {
        case 'login_ack':
          Logger.print('[CS WS] 登录确认: ${msg['data']}');
          // 拉取离线消息
          _ws?.add(jsonEncode({'type': 'pull_offline'}));
          break;

        case 'message':
          _handleIncomingMessage(msg['data']);
          break;

        case 'pull_offline_ack':
          final messages = msg['data']?['messages'] as List<dynamic>?;
          if (messages != null) {
            for (final m in messages) {
              _handleIncomingMessage(m);
            }
          }
          break;

        case 'chat_ack':
          Logger.print('[CS WS] 消息发送确认: ${msg['data']}');
          break;

        case 'pong':
          break;

        case 'error':
          Logger.print('[CS WS] 服务端错误: ${msg['data']}');
          break;

        default:
          Logger.print('[CS WS] 未知消息类型: $type');
      }
    } catch (e) {
      Logger.print('[CS WS] 解析消息失败: $e');
    }
  }

  void _handleIncomingMessage(dynamic msgData) {
    if (msgData == null) return;

    try {
      final conversationId = msgData['conversationId'] ?? msgData['conversation_id'] ?? '';
      final senderId = msgData['senderId'] ?? msgData['sender_id'] ?? '';
      final content = msgData['content'] ?? '';
      final messageId = msgData['messageId'] ?? msgData['message_id'] ?? '';

      // 忽略自己发的消息
      if (senderId == _userId) return;

      Logger.print('[CS WS] 收到新消息: conv=$conversationId sender=$senderId content=$content');

      _onMessageController.add(CsMessageData(
        conversationId: conversationId,
        senderId: senderId,
        content: content,
        messageId: messageId,
      ));
    } catch (e) {
      Logger.print('[CS WS] 处理消息失败: $e');
    }
  }

  void _setConnected(bool connected) {
    if (_connected != connected) {
      _connected = connected;
      _onConnectionChanged.add(connected);
    }
  }

  void _scheduleReconnect() {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      Logger.print('[CS WS] 尝试重连...');
      _connect();
    });
  }

  void _cleanup() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    _ws?.close();
    _ws = null;
  }

  /// 发送消息（通过 WebSocket）
  /// [conversationId] 是服务端的 conversation_id，格式为 si_{sorted_id1}_{sorted_id2}
  void sendMessage(String conversationId, String content) {
    if (_ws == null || _ws?.readyState != WebSocket.open) {
      Logger.print('[CS WS] 未连接，无法发送消息');
      return;
    }

    _ws!.add(jsonEncode({
      'type': 'chat',
      'data': {
        'conversation_id': conversationId,
        'msg_type': 1,
        'content': content,
      }
    }));
    Logger.print('[CS WS] 消息已发送: conversationId=$conversationId');
  }

  /// 释放资源
  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _cleanup();
    _onMessageController.close();
    _onConnectionChanged.close();
    _token = null;
    _userId = null;
    Logger.print('[CS WS] 已释放');
  }
}

/// CS WebSocket 收到的消息数据
class CsMessageData {
  final String conversationId;
  final String senderId;
  final String content;
  final String messageId;

  CsMessageData({
    required this.conversationId,
    required this.senderId,
    required this.content,
    required this.messageId,
  });
}