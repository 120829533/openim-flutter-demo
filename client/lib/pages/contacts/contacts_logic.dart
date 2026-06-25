import 'package:flutter_openim_sdk/flutter_openim_sdk.dart';
import 'package:get/get.dart';
import 'package:openim/routes/app_navigator.dart';
import 'package:openim_common/openim_common.dart';

import '../../core/controller/im_controller.dart';
import '../home/home_logic.dart';
import 'select_contacts/select_contacts_logic.dart';

class ContactsLogic extends GetxController
    implements SelectContactsBridge, ScanBridge {
  final imLogic = Get.find<IMController>();
  final homeLogic = Get.find<HomeLogic>();

  final friendApplicationList = <UserInfo>[];

  int get friendApplicationCount => homeLogic.unhandledFriendApplicationCount.value;

  @override
  void onInit() {
    PackageBridge.selectContactsBridge = this;
    PackageBridge.scanBridge = this;

    super.onInit();
  }

  @override
  void onClose() {
    PackageBridge.selectContactsBridge = null;
    PackageBridge.viewUserProfileBridge = null;
    PackageBridge.scanBridge = null;
    super.onClose();
  }

  void newFriend() => AppNavigator.startFriendRequests();

  void myFriend() => AppNavigator.startFriendList();

  void searchContacts() => AppNavigator.startGlobalSearch();

  void addContacts() => AppNavigator.startAddContactsMethod();

  @override
  Future<T?>? selectContacts<T>(
    int type, {
    List<String>? defaultCheckedIDList,
    List? checkedList,
    List<String>? excludeIDList,
    bool openSelectedSheet = false,
    String? groupID,
    String? ex,
  }) =>
      AppNavigator.startSelectContacts(
        action: SelAction.values[type],
        defaultCheckedIDList: defaultCheckedIDList,
        checkedList: checkedList,
        excludeIDList: excludeIDList,
        openSelectedSheet: openSelectedSheet,
        groupID: groupID,
        ex: ex,
      );

  @override
  dynamic viewUserProfile(String userID, String? nickname, String? faceURL, [String? groupID]) =>
      AppNavigator.startUserProfilePane(
        userID: userID,
        nickname: nickname,
        faceURL: faceURL,
        groupID: groupID,
      );

  @override
  scanOutGroupID(String groupID) {}

  @override
  scanOutUserID(String userID) => AppNavigator.startUserProfilePane(userID: userID, offAndToNamed: true);
}
