import 'dart:async';
import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:openim_common/openim_common.dart';

/// 全局 CS 消息缓存
///
/// 在 ConversationLogic 和 ChatLogic 之间共享 CS 会话消息。
class CsMessageStore {
  static final CsMessageStore _instance = CsMessageStore._();
  factory CsMessageStore() => _instance;
  CsMessageStore._();

  /// conversationId -> [Message]
  final _messages = <String, List<Message>>{};

  /// 新消息广播
  final _onNewMessage = StreamController<CsStoreMessage>.broadcast();
  Stream<CsStoreMessage> get onNewMessage => _onNewMessage.stream;

  /// 添加一条 CS 消息
  void addMessage({
    required String conversationId,
    required String senderId,
    required String content,
    required String messageId,
  }) {
    _messages.putIfAbsent(conversationId, () => []);

    // 去重：避免 WebSocket 和离线拉取产生重复消息
    final existing = _messages[conversationId]!.any((m) => m.clientMsgID == messageId);
    if (existing) return;

    final msg = Message(
      clientMsgID: messageId,
      sendID: senderId,
      senderNickname: senderId,
      contentType: MessageType.text,
      textElem: TextElem(content: content),
      sendTime: DateTime.now().millisecondsSinceEpoch,
      status: 2,
      isRead: true,
    );

    _messages[conversationId]!.add(msg);

    _onNewMessage.add(CsStoreMessage(
      conversationId: conversationId,
      message: msg,
    ));
  }

  /// 获取某个会话的所有消息
  List<Message> getMessages(String conversationId) {
    return List.unmodifiable(_messages[conversationId] ?? []);
  }

  /// 添加自己发送的消息
  void addSentMessage({
    required String conversationId,
    required String content,
    required String messageId,
  }) {
    final msg = Message(
      clientMsgID: messageId,
      sendID: 'cs_agent_001',
      senderNickname: '客服',
      contentType: MessageType.text,
      textElem: TextElem(content: content),
      sendTime: DateTime.now().millisecondsSinceEpoch,
      status: 2,
      isRead: true,
    );

    _messages.putIfAbsent(conversationId, () => []);
    _messages[conversationId]!.add(msg);

    _onNewMessage.add(CsStoreMessage(
      conversationId: conversationId,
      message: msg,
    ));
  }

  /// 清除某个会话的消息
  void clearConversation(String conversationId) {
    _messages.remove(conversationId);
  }

  void dispose() {
    _messages.clear();
    _onNewMessage.close();
  }
}

class CsStoreMessage {
  final String conversationId;
  final Message message;
  CsStoreMessage({required this.conversationId, required this.message});
}
