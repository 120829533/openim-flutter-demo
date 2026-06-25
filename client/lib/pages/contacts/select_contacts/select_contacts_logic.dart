import 'package:flutter/material.dart';
import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:get/get.dart';
import 'package:openim/pages/conversation/conversation_logic.dart';
import 'package:openim/routes/app_navigator.dart';
import 'package:openim_common/openim_common.dart';

import 'select_contacts_view.dart';

enum SelAction {
  forward,

  carte,

  recommend,
}

class SelectContactsLogic extends GetxController implements OrganizationMultiSelBridge {
  final checkedList = <String, dynamic>{}.obs;
  final defaultCheckedIDList = <String>{}.obs;
  List<String>? excludeIDList;
  late SelAction action;
  late bool openSelectedSheet;
  String? groupID;
  final conversationList = <ConversationInfo>[].obs;
  String? ex;
  final inputCtrl = TextEditingController();

  @override
  void onInit() {
    action = Get.arguments['action'];
    groupID = Get.arguments['groupID'];
    excludeIDList = Get.arguments['excludeIDList'];
    defaultCheckedIDList.addAll(Get.arguments['defaultCheckedIDList'] ?? []);
    checkedList.addAll(Get.arguments['checkedList'] ?? {});
    openSelectedSheet = Get.arguments['openSelectedSheet'];
    ex = Get.arguments['ex'];
    super.onInit();
  }

  @override
  void onClose() {
    inputCtrl.dispose();
    super.onClose();
  }

  @override
  void onReady() {
    _queryConversationList();
    if (openSelectedSheet) viewSelectedContactsList();
    super.onReady();
  }

  @override
  bool get isMultiModel => action != SelAction.carte;

  bool get hiddenConversations => action == SelAction.carte;

  Future<void> _queryConversationList() async {
    if (!hiddenConversations) {
      final cons = Get.find<ConversationLogic>().list.where((con) => !con.isGroupChat);

      final filteredCons = cons.where((con) => con.conversationType != ConversationType.notification).toList();

      conversationList.addAll(filteredCons);
    }
  }

  static String? parseID(e) {
    if (e is ConversationInfo) {
      return e.userID;
    } else if (e is UserInfo || e is FriendInfo || e is UserFullInfo) {
      return e.userID;
    } else {
      return null;
    }
  }

  static String? parseName(e) {
    if (e is ConversationInfo) {
      return e.showName;
    } else if (e is UserInfo || e is FriendInfo || e is UserFullInfo) {
      return e.nickname;
    } else {
      return null;
    }
  }

  static String? parseFaceURL(e) {
    if (e is ConversationInfo) {
      return e.faceURL;
    } else if (e is UserInfo || e is FriendInfo || e is UserFullInfo) {
      return e.faceURL;
    } else {
      return null;
    }
  }

  @override
  bool isChecked(info) => checkedList.containsKey(parseID(info));

  @override
  bool isDefaultChecked(info) => defaultCheckedIDList.contains(parseID(info));

  @override
  Function()? onTap(dynamic info) => isDefaultChecked(info) ? null : () => toggleChecked(info);

  @override
  removeItem(dynamic info) {
    checkedList.remove(parseID(info));
  }

  @override
  toggleChecked(dynamic info) {
    if (isMultiModel) {
      final key = parseID(info);
      if (checkedList.containsKey(key)) {
        checkedList.remove(key);
      } else {
        checkedList.putIfAbsent(key ?? '', () => info);
      }
    } else {
      confirmSelectedItem(info);
    }
  }

  @override
  updateDefaultCheckedList(List<String> userIDList) async {
    defaultCheckedIDList.addAll(userIDList);
  }

  String get checkedStrTips => checkedList.values.map(parseName).join('、');

  Future<dynamic> viewSelectedContactsList() => Get.bottomSheet(
        SelectedContactsListView(),
        isScrollControlled: true,
      );

  Future<void> selectFromMyFriend() async {
    final result = AppNavigator.startSelectContactsFromFriends();
    if (null != result) {
      Get.back(result: result);
    }
  }

  Future<void> selectTagGroup() async {
    final result = AppNavigator.startSelectContactsFromTag();
    if (null != result) {
      Get.back(result: result);
    }
  }

  Future<void> confirmSelectedList() async {
    if (action == SelAction.forward || action == SelAction.recommend) {
      final sure = await Get.dialog(ForwardHintDialog(
        title: ex ?? '',
        checkedList: checkedList.values.toList(),
      ));
      if (sure == true) {
        Get.back(result: {
          "checkedList": checkedList.values,
        });
      }
    } else {
      Get.back(result: checkedList.value);
    }
  }

  Future<void> confirmSelectedItem(dynamic info) async {
    if (action == SelAction.carte) {
      final sure = await Get.dialog(CustomDialog(
        title: StrRes.sendCarteConfirmHint,
      ));
      if (sure == true) {
        Get.back(result: UserInfo.fromJson(info.toJson()));
      }
    }
  }

  bool get enabledConfirmButton => checkedList.isNotEmpty;

  @override
  Widget get checkedConfirmView => isMultiModel ? CheckedConfirmView() : const SizedBox();
}
