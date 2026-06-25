import 'package:flutter/material.dart';
import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:get/get.dart';
import 'package:openim_common/openim_common.dart';

import 'chat_logic.dart';

class ChatPage extends StatelessWidget {
  final logic = Get.find<ChatLogic>(tag: GetTags.chat);

  ChatPage({super.key});

  Widget _buildItemView(Message message) => ChatItemView(
        key: logic.itemKey(message),
        message: message,
        textScaleFactor: logic.scaleFactor.value,
        allAtMap: logic.getAtMapping(message),
        timelineStr: logic.getShowTime(message),
        sendStatusSubject: logic.sendStatusSub,
        leftNickname: logic.getNewestNickname(message),
        leftFaceUrl: logic.getNewestFaceURL(message),
        rightNickname: logic.senderName,
        rightFaceUrl: OpenIM.iMManager.userInfo.faceURL,
        showLeftNickname: !logic.isSingleChat,
        showRightNickname: !logic.isSingleChat,
        onFailedToResend: () => logic.failedResend(message),
        onClickItemView: () => logic.parseClickEvent(message),
        visibilityChange: (msg, visible) {
          logic.markMessageAsRead(message, visible);
        },
        onLongPressRightAvatar: () {},
        onTapLeftAvatar: () {
          logic.onTapLeftAvatar(message);
        },
        onVisibleTrulyText: (text) {
          logic.copyTextMap[message.clientMsgID] = text;
        },
        customTypeBuilder: _buildCustomTypeItemView,
        patterns: <MatchPattern>[
          MatchPattern(
            type: PatternType.email,
            onTap: logic.clickLinkText,
          ),
          MatchPattern(
            type: PatternType.url,
            onTap: logic.clickLinkText,
          ),
          MatchPattern(
            type: PatternType.mobile,
            onTap: logic.clickLinkText,
          ),
          MatchPattern(
            type: PatternType.tel,
            onTap: logic.clickLinkText,
          ),
        ],
        mediaItemBuilder: (context, message) {
          return _buildMediaItem(context, message);
        },
        onTapUserProfile: handleUserProfileTap,
      );

  void handleUserProfileTap(({String userID, String name, String? faceURL, String? groupID}) userProfile) {
    final userInfo = UserInfo(userID: userProfile.userID, nickname: userProfile.name, faceURL: userProfile.faceURL);
    logic.viewUserInfo(userInfo);
  }

  Widget? _buildMediaItem(BuildContext context, Message message) {
    if (message.contentType != MessageType.picture && message.contentType != MessageType.video) {
      return null;
    }

    return GestureDetector(
      onTap: () async {
        try {
          IMUtils.previewMediaFile(
              context: context,
              message: message,
              onAutoPlay: (index) {
                return !logic.playOnce;
              },
              muted: logic.rtcIsBusy,
              onPageChanged: (index) {
                logic.playOnce = true;
              }).then((value) {
            logic.playOnce = false;
          });
        } catch (e) {
          IMViews.showToast(e.toString());
        }
      },
      child: Hero(
        tag: message.clientMsgID!,
        child: _buildMediaContent(message),
        placeholderBuilder: (BuildContext context, Size heroSize, Widget child) => child,
      ),
    );
  }

  Widget _buildMediaContent(Message message) {
    final isOutgoing = message.sendID == OpenIM.iMManager.userID;

    if (message.isVideoType) {
      return const SizedBox();
    } else {
      return ChatPictureView(
        isISend: isOutgoing,
        message: message,
      );
    }
  }

  CustomTypeInfo? _buildCustomTypeItemView(_, Message message) {
    final data = IMUtils.parseCustomMessage(message);
    if (null != data) {
      final viewType = data['viewType'];
      if (viewType == CustomMessageType.call) {
        final type = data['type'];
        final content = data['content'];
        final view = ChatCallItemView(type: type, content: content);
        return CustomTypeInfo(view);
      } else if (viewType == CustomMessageType.deletedByFriend || viewType == CustomMessageType.blockedByFriend) {
        final view = ChatFriendRelationshipAbnormalHintView(
          name: logic.nickname.value,
          onTap: logic.sendFriendVerification,
          blockedByFriend: viewType == CustomMessageType.blockedByFriend,
          deletedByFriend: viewType == CustomMessageType.deletedByFriend,
        );
        return CustomTypeInfo(view, false, false);
      } else if (viewType == CustomMessageType.removedFromGroup) {
        return CustomTypeInfo(
          StrRes.removedFromGroupHint.toText..style = Styles.ts_8E9AB0_12sp,
          false,
          false,
        );
      } else if (viewType == CustomMessageType.groupDisbanded) {
        return CustomTypeInfo(
          StrRes.groupDisbanded.toText..style = Styles.ts_8E9AB0_12sp,
          false,
          false,
        );
      }
    }
    return null;
  }

  Widget? get _groupCallHintView => null;

  @override
  Widget build(BuildContext context) {
    try {
      return WillPopScope(
        onWillPop: logic.willPop(),
        child: Obx(() {
          try {
            return Scaffold(
                backgroundColor: Styles.c_F0F2F6,
                appBar: TitleBar.chat(
                  title: logic.nickname.value,
                  member: logic.memberStr,
                  onCloseMultiModel: logic.exit,
                  onClickMoreBtn: logic.chatSetup,
                  onClickCallBtn: logic.isGroupChat ? null : logic.call,
                ),
                body: SafeArea(
                  child: Column(
                    children: [
                      // 调试信息：显示会话ID和消息数
                      Obx(() {
                        final convId = logic.conversationInfo.conversationID;
                        return Container(
                          width: double.infinity,
                          color: logic.isCsConversation ? Colors.orange.shade100 : Colors.green.shade100,
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          child: Text(
                            'CS=${logic.isCsConversation} | msgs=${logic.messageList.length} | convId=${convId.length > 30 ? '${convId.substring(0, 30)}...' : convId}',
                            style: const TextStyle(fontSize: 10, color: Colors.black87),
                          ),
                        );
                      }),
                      Expanded(
                        child: WaterMarkBgView(
                          text: '',
                          path: logic.background.value,
                          backgroundColor: Styles.c_FFFFFF,
                          floatView: _groupCallHintView,
                          bottomView: ChatInputBox(
                      forceCloseToolboxSub: logic.forceCloseToolbox,
                      controller: logic.inputCtrl,
                      focusNode: logic.focusNode,
                      isNotInGroup: logic.isInvalidGroup,
                      directionalText: logic.directionalText(),
                      onCloseDirectional: logic.onClearDirectional,
                      onSend: (v) => logic.sendTextMsg(),
                      toolbox: ChatToolBox(
                        onTapAlbum: logic.onTapAlbum,
                        onTapCall: logic.isGroupChat ? null : logic.call,
                      ),
                      voiceRecordBar: const SizedBox(),
                    ),
                    child: ChatListView(
                      onTouch: () => logic.closeToolbox(),
                      itemCount: logic.messageList.length,
                      controller: logic.scrollController,
                      onScrollToBottomLoad: logic.onScrollToBottomLoad,
                      onScrollToTop: logic.onScrollToTop,
                      itemBuilder: (_, index) {
                        try {
                          final message = logic.indexOfMessage(index);
                          return Obx(() => _buildItemView(message));
                        } catch (e, s) {
                          Logger.print('[ChatView] itemBuilder 异常: $e $s');
                          return const SizedBox.shrink();
                        }
                      },
                    ),
                  ),
                        ),
                      ],
                    ),
                  ),
                );
          } catch (e, s) {
            Logger.print('[ChatView] Obx build 异常: $e $s');
            return _buildErrorView('聊天页面加载失败: $e');
          }
        }),
      );
    } catch (e, s) {
      Logger.print('[ChatView] build 异常: $e $s');
      return _buildErrorView('页面加载失败: $e');
    }
  }

  Widget _buildErrorView(String msg) {
    return Scaffold(
      backgroundColor: Styles.c_F0F2F6,
      appBar: AppBar(title: const Text('聊天')),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.grey),
            const SizedBox(height: 16),
            Text(msg, style: const TextStyle(color: Colors.grey, fontSize: 14)),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () => Get.back(),
              child: const Text('返回'),
            ),
          ],
        ),
      ),
    );
  }
}
