part of 'app_pages.dart';

abstract class AppRoutes {
  static const notFound = '/not-found';
  static const splash = '/splash';
  static const login = '/login';
  static const home = '/home';
  static const chat = '/chat';
  static const chatSetup = '/chat_setup';
  static const userProfilePanel = '/user_profile_panel';
  static const personalInfo = '/personal_info';
  static const friendSetup = '/friend_setup';
  static const setFriendRemark = '/set_friend_remark';
  static const myInfo = '/my_info';
  static const editMyInfo = '/edit_my_info';
  static const accountSetup = '/account_setup';
  static const blacklist = '/blacklist';
  static const languageSetup = '/language_setup';
  static const aboutUs = '/about_us';
  static const selectContacts = '/select_contacts';
  static const globalSearch = '/global_search';
  static const expandChatHistory = '/expand_chat_history';
  static const register = '/register';
  static const verifyPhone = '/verify_phone';
  static const setPassword = '/set_password';
  static const setSelfInfo = '/set_self_info';
  static const forgetPassword = '/forget_password';
  static const resetPassword = '/reset_password';
}

extension RoutesExtension on String {
  String toRoute() => '/${toLowerCase()}';
}
