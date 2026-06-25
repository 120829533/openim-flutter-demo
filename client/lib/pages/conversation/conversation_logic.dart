import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_easyloading/flutter_easyloading.dart';
import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:get/get.dart';
import 'package:openim_common/openim_common.dart';
import 'package:pull_to_refresh_new/pull_to_refresh.dart';

import '../../core/controller/app_controller.dart';
import '../../core/controller/im_controller.dart';
import '../../core/cs_websocket.dart';
import '../../core/im_callback.dart';
import '../../routes/app_navigator.dart';
import '../home/home_logic.dart';

class ConversationLogic extends GetxController {
  final popCtrl = CustomPopupMenuController();
  final list = <ConversationInfo>[].obs;
  final imLogic = Get.find<IMController>();
  final homeLogic = Get.find<HomeLogic>();
  final appLogic = Get.find<AppController>();
  final refreshController = RefreshController();
  final tempDraftText = <String, String>{};
  final pageSize = 400;

  final imStatus = IMSdkStatus.connectionSucceeded.obs;
  bool reInstall = false;

  final onChangeConversations = <ConversationInfo>[];

  /// CS 访客名称映射：openim_user_id -> visitor_name
  final _visitorNames = <String, String>{};
  /// CS 访客头像映射：openim_user_id -> avatar
  final _visitorAvatars = <String, String>{};
  /// 当前用户是否为客服
  bool _isCsAgent = false;
  /// CS 本地会话缓存：conversationId -> ConversationInfo
  final _csConversations = <String, ConversationInfo>{};
  /// CS WebSocket 消息订阅
  StreamSubscription<CsMessageData>? _csMessageSub;

  @override
  void onInit() {
    getFirstPage();
    imLogic.conversationAddedSubject.listen(onChanged);
    imLogic.conversationChangedSubject.listen(onChanged);
    imLogic.imSdkStatusSubject.listen((value) async {
      final status = value.status;
      final appReInstall = value.reInstall;
      final progress = value.progress;
      imStatus.value = status;

      if (status == IMSdkStatus.syncStart) {
        reInstall = appReInstall;
        if (reInstall) {
          EasyLoading.showProgress(0, status: StrRes.synchronizing);
        }
      }

      Logger.print('IM SDK Status: $status, reinstall: $reInstall, progress: $progress');

      if (status == IMSdkStatus.syncProgress && reInstall) {
        final p = (progress!).toDouble() / 100.0;

        EasyLoading.showProgress(p, status: '${StrRes.synchronizing}(${(p * 100.0).truncate()}%)');
      } else if (status == IMSdkStatus.syncEnded || status == IMSdkStatus.syncFailed) {
        EasyLoading.dismiss();
        if (reInstall) {
          onRefresh();
          reInstall = false;
        }
      }
    });

    // 检查是否为客服账号，加载访客名称
    _initCsAgent();
    super.onInit();
  }

  /// 初始化客服相关功能
  void _initCsAgent() async {
    final userId = DataSp.userID;
    if (userId == 'cs_agent_001') {
      _isCsAgent = true;
      // 加载访客名称映射
      _loadVisitorNames();
      // 监听 CS WebSocket 消息，收到新消息时更新列表
      _csMessageSub = CsWebSocketService().onMessage.listen((msg) {
        Logger.print('[Conv] CS 新消息: sender=${msg.senderId} content=${msg.content}');
        _handleCsIncomingMessage(msg);
      });
    }
  }

  /// 处理 CS WebSocket 收到的新消息
  void _handleCsIncomingMessage(CsMessageData msg) {
    // 确保访客名称已缓存
    if (!_visitorNames.containsKey(msg.senderId)) {
      _loadVisitorName(msg.senderId);
    }

    final convId = 'cs_conv_${msg.senderId}';
    final existing = _csConversations[convId];
    if (existing != null) {
      // 更新已有会话
      existing.unreadCount = (existing.unreadCount ?? 0) + 1;
      existing.latestMsg = Message(
        sendID: msg.senderId,
        senderNickname: _visitorNames[msg.senderId] ?? msg.senderId,
        contentType: MessageType.text,
        textElem: TextElem(content: msg.content),
        sendTime: DateTime.now().millisecondsSinceEpoch,
      );
      existing.latestMsgSendTime = DateTime.now().millisecondsSinceEpoch;
    } else {
      // 新建会话
      final visitorName = _visitorNames[msg.senderId] ?? msg.senderId;
      final avatar = _visitorAvatars[msg.senderId];
      final newConv = ConversationInfo(
        conversationID: convId,
        userID: msg.senderId,
        showName: visitorName,
        faceURL: avatar,
        conversationType: ConversationType.single,
        unreadCount: 1,
        latestMsg: Message(
          sendID: msg.senderId,
          senderNickname: visitorName,
          contentType: MessageType.text,
          textElem: TextElem(content: msg.content),
          sendTime: DateTime.now().millisecondsSinceEpoch,
        ),
        latestMsgSendTime: DateTime.now().millisecondsSinceEpoch,
      );
      _csConversations[convId] = newConv;
    }
    // 刷新 UI
    _mergeAndRefreshList();
  }

  /// 动态加载单个访客名称
  void _loadVisitorName(String visitorUserId) async {
    try {
      final dio = Dio(BaseOptions(baseUrl: Config.imApiUrl));
      final resp = await dio.get('/api/cs/visitor-names');
      final data = resp.data;
      if (data is Map && data['errCode'] == 0) {
        final visitors = data['data']?['visitors'] as Map<String, dynamic>?;
        if (visitors != null && visitors.containsKey(visitorUserId)) {
          final v = visitors[visitorUserId] as Map<String, dynamic>?;
          if (v != null) {
            _visitorNames[visitorUserId] = v['name'] as String? ?? visitorUserId;
            _visitorAvatars[visitorUserId] = v['avatar'] as String? ?? '';
          }
        }
      }
    } catch (e) {
      Logger.print('[Conv] 加载访客名称失败: $e');
    }
  }

  /// 合并 OpenIM SDK 会话和 CS 本地会话，刷新列表
  void _mergeAndRefreshList() async {
    List<ConversationInfo> sdkConvs;
    try {
      sdkConvs = await OpenIM.iMManager.conversationManager.getConversationListSplit(offset: 0, count: pageSize);
    } catch (e) {
      sdkConvs = [];
    }
    final merged = <ConversationInfo>[...sdkConvs];
    // 插入 CS 会话（去重）
    for (final csConv in _csConversations.values) {
      final idx = merged.indexWhere((e) => e.conversationID == csConv.conversationID);
      if (idx >= 0) {
        merged[idx] = csConv;
      } else {
        merged.add(csConv);
      }
    }
    // 按时间排序
    merged.sort((a, b) => (b.latestMsgSendTime ?? 0).compareTo(a.latestMsgSendTime ?? 0));
    list.assignAll(merged);
  }

  /// 从 API 加载访客名称映射
  void _loadVisitorNames() async {
    try {
      final dio = Dio(BaseOptions(baseUrl: Config.imApiUrl));
      final resp = await dio.get('/api/cs/visitor-names');
      final data = resp.data;
      if (data is Map && data['errCode'] == 0) {
        final visitors = data['data']?['visitors'] as Map<String, dynamic>?;
        if (visitors != null) {
          _visitorNames.clear();
          _visitorAvatars.clear();
          for (final entry in visitors.entries) {
            final v = entry.value as Map<String, dynamic>?;
            if (v != null) {
              _visitorNames[entry.key] = v['name'] as String? ?? entry.key;
              _visitorAvatars[entry.key] = v['avatar'] as String? ?? '';
            }
          }
          Logger.print('[Conv] 已加载 ${_visitorNames.length} 个访客名称');
        }
      }
    } catch (e) {
      Logger.print('[Conv] 加载访客名称失败: $e');
    }
  }

  @override
  void onClose() {
    list.clear();
    reInstall = false;
    _csMessageSub?.cancel();
    _csConversations.clear();
    super.onClose();
  }

  void onChanged(List<ConversationInfo> newList) {
    if (reInstall) {
      onChangeConversations.addAll(newList);
    }
    for (var newValue in newList) {
      Logger.print('======== conversation changed: ${newValue.toJson()} ========');
      list.removeWhere((e) => e.conversationID == newValue.conversationID);
    }

    if (newList.length > pageSize) {
      final tempList = newList;

      while (true) {
        final temp = tempList.sublist(0, pageSize);
        list.insertAll(0, temp);
        _sortConversationList();

        if (tempList.length <= pageSize) {
          break;
        }

        tempList.removeRange(0, pageSize);
      }
    } else {
      list.insertAll(0, newList);
      _sortConversationList();
      Logger.print(
          '======== conversation sort result: ${list.where((e) => e.unreadCount > 0).toList().map((e) => '${e.showName} [${e.conversationID}]: ${e.unreadCount}')} ========');
    }
  }

  void promptSoundOrNotification(ConversationInfo info) {
    if (imLogic.userInfo.value.globalRecvMsgOpt == 0 &&
        info.recvMsgOpt == 0 &&
        info.unreadCount > 0 &&
        info.latestMsg?.sendID != OpenIM.iMManager.userID) {
      appLogic.promptSoundOrNotification(info.latestMsg!.seq!);
    }
  }

  String getConversationID(ConversationInfo info) {
    return info.conversationID;
  }

  String? getPrefixTag(ConversationInfo info) {
    if (info.groupAtType == GroupAtType.groupNotification) {
      return '[${StrRes.groupAc}]';
    }

    return null;
  }

  String getContent(ConversationInfo info) {
    try {
      if (null != info.draftText && '' != info.draftText) {
        var map = json.decode(info.draftText!);
        String text = map['text'];
        if (text.isNotEmpty) {
          return text;
        }
      }

      if (null == info.latestMsg) return "";

      final text = IMUtils.parseNtf(info.latestMsg!, isConversation: true);
      if (text != null) return text;
      if (info.isSingleChat || info.latestMsg!.sendID == OpenIM.iMManager.userID) {
        return IMUtils.parseMsg(info.latestMsg!, isConversation: true);
      }

      return "${info.latestMsg!.senderNickname}: ${IMUtils.parseMsg(info.latestMsg!, isConversation: true)} ";
    } catch (e, s) {
      Logger.print('------e:$e s:$s');
    }
    return '[${StrRes.unsupportedMessage}]';
  }

  String? getAvatar(ConversationInfo info) {
    return info.faceURL;
  }

  bool isGroupChat(ConversationInfo info) {
    return info.isGroupChat;
  }

  String getShowName(ConversationInfo info) {
    // CS 客服会话：优先使用访客名称
    if (_isCsAgent && info.isSingleChat) {
      final visitorName = _visitorNames[info.userID];
      if (visitorName != null && visitorName.isNotEmpty) {
        return visitorName;
      }
    }
    if (info.showName == null || info.showName.isBlank!) {
      return info.userID!;
    }
    return info.showName!;
  }

  /// 判断是否为 CS 客服会话
  bool isCsConversation(ConversationInfo info) {
    if (!_isCsAgent) return false;
    return _csConversations.containsKey(info.conversationID);
  }

  String getTime(ConversationInfo info) {
    return IMUtils.getChatTimeline(info.latestMsgSendTime!);
  }

  int getUnreadCount(ConversationInfo info) {
    return info.unreadCount;
  }

  bool existUnreadMsg(ConversationInfo info) {
    return getUnreadCount(info) > 0;
  }

  bool isUserGroup(int index) => list.elementAt(index).isGroupChat;

  String? get imSdkStatus {
    switch (imStatus.value) {
      case IMSdkStatus.syncStart:
      case IMSdkStatus.synchronizing:
      case IMSdkStatus.syncProgress:
        return StrRes.synchronizing;
      case IMSdkStatus.syncFailed:
        return StrRes.syncFailed;
      case IMSdkStatus.connecting:
        return StrRes.connecting;
      case IMSdkStatus.connectionFailed:
        return StrRes.connectionFailed;
      case IMSdkStatus.connectionSucceeded:
      case IMSdkStatus.syncEnded:
        return null;
    }
  }

  bool get isFailedSdkStatus =>
      imStatus.value == IMSdkStatus.connectionFailed || imStatus.value == IMSdkStatus.syncFailed;

  void _sortConversationList() => OpenIM.iMManager.conversationManager.simpleSort(list);

  void onRefresh() async {
    late List<ConversationInfo> list;
    try {
      list = await _request();
      this.list.assignAll(list);

      if (list.isEmpty || list.length < pageSize) {
        refreshController.loadNoData();
      } else {
        refreshController.loadComplete();
      }
    } finally {
      refreshController.refreshCompleted();
    }
  }

  static Future<List<ConversationInfo>> getConversationFirstPage() async {
    final result = await OpenIM.iMManager.conversationManager.getConversationListSplit(offset: 0, count: 400);

    return result;
  }

  void getFirstPage() async {
    final result = homeLogic.conversationsAtFirstPage;

    list.assignAll(result);
    _sortConversationList();
  }

  void clearConversations() {
    list.clear();
  }

  Future<List<ConversationInfo>> _request() async {
    final temp = <ConversationInfo>[];

    while (true) {
      var result = await OpenIM.iMManager.conversationManager.getConversationListSplit(
        offset: temp.length,
        count: pageSize,
      );
      if (onChangeConversations.isNotEmpty) {
        final bSet = Set.from(onChangeConversations);

        Logger.print('replace conversation: [${onChangeConversations.length}], $bSet');

        for (int i = 0; i < result.length; i++) {
          final info = result[i];

          if (bSet.contains(info)) {
            result[i] = onChangeConversations[onChangeConversations.indexOf(info)];
          }
        }
      }
      temp.addAll(result);

      if (result.length < pageSize) {
        break;
      }
    }
    onChangeConversations.clear();

    return temp;
  }

  bool isValidConversation(ConversationInfo info) {
    return info.isValid;
  }

  static Future<ConversationInfo> _createConversation({
    required String sourceID,
    required int sessionType,
  }) =>
      LoadingView.singleton.wrap(
          asyncFunction: () => OpenIM.iMManager.conversationManager.getOneConversation(
                sourceID: sourceID,
                sessionType: sessionType,
              ));

  Future<bool> _jumpOANtf(ConversationInfo info) async {
    if (info.conversationType == ConversationType.notification) {
      return true;
    }
    return false;
  }

  void toChat({
    bool offUntilHome = true,
    String? userID,
    String? groupID,
    String? nickname,
    String? faceURL,
    int? sessionType,
    ConversationInfo? conversationInfo,
    Message? searchMessage,
  }) async {
    conversationInfo ??= await _createConversation(
      sourceID: userID ?? groupID!,
      sessionType: userID == null ? sessionType! : ConversationType.single,
    );

    if (await _jumpOANtf(conversationInfo)) return;

    await AppNavigator.startChat(
      offUntilHome: offUntilHome,
      draftText: conversationInfo.draftText,
      conversationInfo: conversationInfo,
      searchMessage: searchMessage,
    );

    bool equal(e) => e.conversationID == conversationInfo?.conversationID;

    var groupAtType = list.firstWhereOrNull(equal)?.groupAtType;
    if (groupAtType != GroupAtType.atNormal) {
      OpenIM.iMManager.conversationManager.resetConversationGroupAtType(
        conversationID: conversationInfo.conversationID,
      );
    }
  }

  dynamic addFriend() => AppNavigator.startAddContactsBySearch(searchType: null);
  dynamic createGroup() => AppNavigator.startCreateGroup(defaultCheckedList: [OpenIM.iMManager.userInfo]);
  dynamic addGroup() => AppNavigator.startAddContactsBySearch(searchType: null);

  void globalSearch() => AppNavigator.startGlobalSearch();
}
