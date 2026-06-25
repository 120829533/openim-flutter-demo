import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:get/get.dart';
import 'package:openim_common/openim_common.dart';

import 'app_pages.dart';

class AppNavigator {
  AppNavigator._();

  static void startLogin() {
    Get.offAllNamed(AppRoutes.login);
  }

  static void startBackLogin() {
    Get.until((route) => Get.currentRoute == AppRoutes.login);
  }

  static void startMain({bool isAutoLogin = false, List<ConversationInfo>? conversations}) {
    Get.offAllNamed(
      AppRoutes.home,
      arguments: {'isAutoLogin': isAutoLogin, 'conversations': conversations},
    );
  }

  static void startSplashToMain({bool isAutoLogin = false, List<ConversationInfo>? conversations}) {
    Get.offAndToNamed(
      AppRoutes.home,
      arguments: {'isAutoLogin': isAutoLogin, 'conversations': conversations},
    );
  }

  static void startBackMain() {
    Get.until((route) => Get.currentRoute == AppRoutes.home);
  }

  static Future<T?>? startChat<T>({
    required ConversationInfo conversationInfo,
    bool offUntilHome = true,
    String? draftText,
    Message? searchMessage,
  }) async {
    GetTags.createChatTag();

    final arguments = {
      'draftText': draftText,
      'conversationInfo': conversationInfo,
      'searchMessage': searchMessage,
    };

    return offUntilHome
        ? Get.offNamedUntil(
            AppRoutes.chat,
            (route) => route.settings.name == AppRoutes.home,
            arguments: arguments,
          )
        : Get.toNamed(
            AppRoutes.chat,
            arguments: arguments,
            preventDuplicates: false,
          );
  }

  static Future<dynamic>? startChatSetup({
    required ConversationInfo conversationInfo,
  }) =>
      Get.toNamed(AppRoutes.chatSetup, arguments: {
        'conversationInfo': conversationInfo,
      });

  static Future<dynamic>? startGlobalSearch() => Get.toNamed(AppRoutes.globalSearch);

  static Future<dynamic>? startExpandChatHistory({
    required SearchResultItems searchResultItems,
    required String defaultSearchKey,
  }) =>
      Get.toNamed(AppRoutes.expandChatHistory, arguments: {
        'searchResultItems': searchResultItems,
        'defaultSearchKey': defaultSearchKey,
      });

  static Future<dynamic>? startRegister() => Get.toNamed(AppRoutes.register);

  static void startVerifyPhone({
    String? phoneNumber,
    String? email,
    required String areaCode,
    required int usedFor,
    String? invitationCode,
  }) =>
      Get.toNamed(AppRoutes.verifyPhone, arguments: {
        'phoneNumber': phoneNumber,
        'email': email,
        'areaCode': areaCode,
        'usedFor': usedFor,
        'invitationCode': invitationCode,
      });

  static void startSetPassword({
    String? phoneNumber,
    String? email,
    required String areaCode,
    required int usedFor,
    required String verificationCode,
    String? invitationCode,
  }) =>
      Get.toNamed(AppRoutes.setPassword, arguments: {
        'phoneNumber': phoneNumber,
        'email': email,
        'areaCode': areaCode,
        'usedFor': usedFor,
        'verificationCode': verificationCode,
        'invitationCode': invitationCode
      });

  static void startSetSelfInfo({
    String? phoneNumber,
    String? email,
    String? account,
    required String areaCode,
    required password,
    required int usedFor,
    required String verificationCode,
    String? invitationCode,
  }) =>
      Get.toNamed(AppRoutes.setSelfInfo, arguments: {
        'phoneNumber': phoneNumber,
        'email': email,
        'account': account,
        'areaCode': areaCode,
        'password': password,
        'usedFor': usedFor,
        'verificationCode': verificationCode,
        'invitationCode': invitationCode
      });

  static Future<dynamic>? startForgetPassword() => Get.toNamed(AppRoutes.forgetPassword);

  static void startResetPassword({
    String? phoneNumber,
    String? email,
    String? account,
    required String areaCode,
    required String verificationCode,
  }) =>
      Get.toNamed(AppRoutes.resetPassword, arguments: {
        'phoneNumber': phoneNumber,
        'email': email,
        'account': account,
        'areaCode': areaCode,
        'usedFor': 2,
        'verificationCode': verificationCode,
      });

  // Stub methods for deleted features
  static startUserProfilePane({required String userID, String? groupID, String? nickname, String? faceURL, bool offAllWhenDelFriend = false, bool offAndToNamed = false, bool forceCanAdd = false}) {}
  static startPersonalInfo({required String userID}) {}
  static startFriendSetup({required String userID}) {}
  static startSetFriendRemark() {}
  static startSendVerificationApplication({String? userID, String? groupID, dynamic joinGroupMethod}) {}
  static startGroupProfilePanel({required String groupID, required dynamic joinGroupMethod, bool offAndToNamed = false}) {}
  static startMyInfo() {}
  static startEditMyInfo({dynamic attr, int? maxLength}) {}
  static startAccountSetup() {}
  static startBlacklist() {}
  static startLanguageSetup() {}
  static startAboutUs() {}
  static startGroupChatSetup({required ConversationInfo conversationInfo}) {}
  static startGroupManage({required dynamic groupInfo}) {}
  static startEditGroupName({required dynamic type, String? faceUrl}) {}
  static startGroupMemberList({required dynamic groupInfo, dynamic opType}) {}
  static startSearchGroupMember({required dynamic groupInfo, dynamic opType}) {}
  static startGroupQrcode() {}
  static startFriendRequests() {}
  static startProcessFriendRequests({required dynamic applicationInfo}) {}
  static startGroupRequests() {}
  static startProcessGroupRequests({required dynamic applicationInfo}) {}
  static startFriendList() {}
  static startGroupList() {}
  static startSelectContacts({required dynamic action, List<String>? defaultCheckedIDList, List<dynamic>? checkedList, List<String>? excludeIDList, bool openSelectedSheet = false, String? groupID, String? ex}) {}
  static startSelectContactsFromFriends() {}
  static startSelectContactsFromGroup() {}
  static startSelectContactsFromSearch() {}
  static startCreateGroup({List<UserInfo> defaultCheckedList = const []}) {}
  static startSelectContactsFromTag() {}
  static startAddContactsMethod() {}
  static startAddContactsBySearch({required dynamic searchType}) {}
}
