# OpenIM Flutter Demo 项目代码文档

> **版本**：v1.0.0
> **最后更新**：2026-06-24
> **适用对象**：开发者、架构师、运维人员
> **维护机制**：详见文末「文档维护与更新机制」章节

---

## 目录

1. [项目概述](#1-项目概述)
2. [项目架构概述](#2-项目架构概述)
3. [技术选型依据](#3-技术选型依据)
4. [功能模块详细说明](#4-功能模块详细说明)
5. [核心算法与实现](#5-核心算法与实现)
6. [API 接口规范](#6-api-接口规范)
7. [数据流程设计](#7-数据流程设计)
8. [关键代码解析](#8-关键代码解析)
9. [数据库设计](#9-数据库设计)
10. [开发环境配置指南](#10-开发环境配置指南)
11. [使用示例](#11-使用示例)
12. [代码注释规范](#12-代码注释规范)
13. [文档维护与更新机制](#13-文档维护与更新机制)

---

## 1. 项目概述

### 1.1 项目简介

OpenIM Flutter Demo 是基于开源 OpenIM SDK 构建的即时通讯（IM）应用参考实现。项目采用 **前后端分离 + 微服务** 架构，提供完整的即时通讯解决方案，可作为 Twilio、Sendbird 等云服务的开源替代方案。

项目整体由三大部分组成：

| 组成部分 | 技术栈 | 说明 |
|---------|--------|------|
| **Flutter 客户端** | Flutter 3.32+ / Dart 3.0+ / GetX | 跨平台 IM 客户端，支持 iOS 13+ 与 Android（minSdk 24） |
| **后端服务集群** | Python(FastAPI) + Java(Spring Boot) + Python(文件服务) | 业务逻辑、消息核心、对象存储三服务解耦 |
| **基础设施** | MySQL 8.0 + Redis 7 + MinIO + Nginx | 数据持久化、缓存、对象存储、反向代理 |

### 1.2 设计理念

- **SDK 兼容优先**：后端通过 OpenIM Chat API 兼容层（`openim_compat`），使未经修改的 OpenIM Flutter SDK 可直接对接自建后端。
- **服务职责单一**：Python 服务负责业务逻辑，Java 服务专注实时消息与长连接，文件服务独立处理对象存储。
- **共享存储解耦**：服务间通过共享 MySQL 表与 Redis 键空间协调状态，避免直接 RPC 耦合。
- **GetX 全栈架构**：客户端统一使用 GetX 实现状态管理、依赖注入与路由导航。

### 1.3 核心特性

- 账号：手机号/邮箱注册、验证码登录、密码管理
- 好友：查找、申请、添加、删除、备注、黑名单
- 群组：创建、解散、邀请、转让、审批
- 消息：文本/图片/视频/语音/文件/位置/名片/自定义，离线消息、漫游消息、消息撤回
- 会话：置顶、免打扰、已读、草稿
- 音视频：一对一音视频通话（基于 LiveKit）
- 推送：在线实时推送、离线推送（个推/Firebase）
- 容量：1 万好友、10 万人大群、秒级同步

---

## 2. 项目架构概述

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        客户端层 (Flutter)                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │  会话列表 │  │  聊天页  │  │  通讯录  │  │  我的/设置       │  │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └────────┬─────────┘  │
│        └─────────────┴─────────────┴───────────────┘            │
│                          GetX 控制器层                           │
│   IMController / AppController / CacheController / PushController│
│        ┌──────────────────────────────────────────┐             │
│        │       openim_common (内部共享包)          │             │
│        │  Apis / HttpUtil / DataSp / Widgets       │             │
│        └──────────────────┬───────────────────────┘             │
└───────────────────────────┼─────────────────────────────────────┘
                            │ HTTPS / WSS
┌───────────────────────────┼─────────────────────────────────────┐
│                  Nginx 反向代理 (80/443)                          │
│        / ──────────────► Python 业务 API                         │
│        /ws ───────────► Java WebSocket                           │
│        /api/message/ ─► Java 消息 REST                           │
│        /file/ ────────► File 文件服务                            │
└───────────────────────────┼─────────────────────────────────────┘
                            │
┌──────────────┬────────────┴───────────┬──────────────┐
│  Python 服务 │     Java 服务          │  文件服务     │
│  (FastAPI)   │     (Spring Boot)      │  (FastAPI)   │
│  :8081       │     :8082              │  :8083       │
│              │                        │              │
│ 认证/用户    │ WebSocket 网关         │ 图片压缩     │
│ 会话/设置    │ 消息收发/撤回           │ 文件上传     │
│ i18n/版本    │ 离线推送               │ MinIO 适配   │
│ OpenIM兼容层 │ 消息历史/搜索           │              │
└──────┬───────┴──────────┬─────────────┴──────┬───────┘
       │                  │                     │
       ▼                  ▼                     ▼
┌────────────┐    ┌────────────┐        ┌────────────┐
│  MySQL 8.0 │    │  Redis 7   │        │   MinIO    │
│  (共享)    │    │  (共享)    │        │ (对象存储) │
└────────────┘    └────────────┘        └────────────┘
```

### 2.2 客户端分层架构

客户端采用清晰的四层分离架构：

```
┌─────────────────────────────────────────────┐
│  表现层 (lib/pages/)                         │
│  每页三件套: *_view.dart / *_logic.dart /    │
│              *_binding.dart                  │
├─────────────────────────────────────────────┤
│  核心控制层 (lib/core/)                      │
│  IMController / AppController / IMCallback  │
├─────────────────────────────────────────────┤
│  共享业务层 (openim_common/)                 │
│  Apis / HttpUtil / DataSp / Models / Widgets│
├─────────────────────────────────────────────┤
│  SDK 层 (flutter_openim_sdk)                │
│  OpenIM.iMManager (WebSocket + 本地DB)      │
└─────────────────────────────────────────────┘
```

### 2.3 后端服务拓扑

| 服务 | 端口 | 框架 | 职责 |
|------|------|------|------|
| Python Service | 8081 | FastAPI + Uvicorn | 账号、用户、会话、设置、i18n、版本、OpenIM 兼容层 |
| Java Service | 8082 | Spring Boot 3.2.5 + WebSocket | 实时消息网关、消息持久化、离线推送 |
| File Service | 8083 | FastAPI + Pillow + MinIO | 图片压缩、文件上传下载、对象存储适配 |
| MySQL | 3306 | MySQL 8.0 | 用户、会话、消息、设置等业务数据 |
| Redis | 6379 | Redis 7 | 在线状态、未读计数、会话列表、验证码、Token |
| MinIO | 9000/9001 | MinIO | S3 兼容对象存储（头像、图片、文件） |
| Nginx | 80/443 | Nginx Alpine | 反向代理、WebSocket 升级、HTTPS 终结 |

---

## 3. 技术选型依据

### 3.1 客户端技术选型

| 技术 | 选型理由 |
|------|---------|
| **Flutter** | 单一代码库同时支持 iOS/Android，高性能渲染，丰富的插件生态 |
| **GetX** | 集成状态管理、依赖注入、路由导航三合一，减少样板代码；`Bindings` 实现懒加载控制器 |
| **flutter_openim_sdk** | OpenIM 官方 Flutter SDK，封装 WebSocket 长连接与本地数据库 |
| **Dio + TalkerDioLogger** | 强大的 HTTP 客户端，拦截器机制便于统一处理鉴权与日志 |
| **Hive** | 轻量级 NoSQL 本地存储，用于通话记录等结构化数据 |
| **RxDart** | 将 SDK 回调转换为响应式流，支持多订阅者与背压控制 |
| **MediaKit / Chewie** | 跨平台视频播放，用于视频消息预览 |
| **Firebase Messaging** | 海外离线推送方案，与个推形成互补 |

### 3.2 后端技术选型

| 技术 | 选型理由 |
|------|---------|
| **FastAPI (Python)** | 异步高性能，自动生成 OpenAPI 文档，适合快速开发业务 API |
| **Spring Boot (Java)** | 成熟的企业级框架，原生 WebSocket 支持，JPA 简化数据访问 |
| **aiomysql / async Redis** | 异步驱动，与 FastAPI 事件循环契合，高并发友好 |
| **MinIO** | S3 兼容的私有对象存储，可平滑迁移至 COS/OSS/S3 |
| **Pillow** | Python 图像处理标准库，实现图片压缩与缩略图生成 |
| **JWT + bcrypt** | 无状态认证 + 安全密码哈希，水平扩展友好 |
| **Docker Compose** | 一键编排多服务，开发/部署环境一致 |

---

## 4. 功能模块详细说明

### 4.1 客户端模块

客户端页面位于 [lib/pages/](file:///home/bing/openim-flutter-demo/lib/pages)，采用 GetX 三件套模式（View/Logic/Binding）。

#### 4.1.1 启动与登录模块

| 页面 | 路由 | 功能说明 |
|------|------|---------|
| Splash | `/splash` | 等待 SDK 初始化，自动登录或跳转登录页 |
| Login | `/login` | 支持手机号/邮箱/账号三种登录方式，密码或验证码 |
| Register | `/register` → `/verify_phone` → `/set_password` → `/set_self_info` | 多步骤注册向导 |
| Forget Password | `/forget_password` → `/reset_password` | 忘记密码重置流程 |

**登录流程**：客户端 MD5 加密密码 → 调用 `Apis.login` → 后端返回 `{userID, imToken, chatToken}` → 存储 `LoginCertificate` → 调用 `imLogic.login(userID, imToken)` 初始化 SDK → 注册 FCM Token → 拉取首页会话 → 跳转主页。

#### 4.1.2 主页与导航模块

[Home 页面](file:///home/bing/openim-flutter-demo/lib/pages/home/home_logic.dart) 使用 `persistent_bottom_nav_bar_v2` 实现底部三 Tab：

- **会话列表**（Conversation）：实时显示会话、未读数、同步状态
- **通讯录**（Contacts）：好友列表、群组列表、好友申请、群申请
- **我的**（Mine）：个人信息、账号设置、黑名单、语言、关于

`HomeLogic` 继承 `SuperController`，监听应用生命周期，处理踢下线、应用锁（密码+生物识别）逻辑。

#### 4.1.3 聊天模块

[Chat 页面](file:///home/bing/openim-flutter-demo/lib/pages/chat/chat_logic.dart) 是最复杂的控制器（约 1100 行），核心功能：

- **消息发送**：文本、图片（压缩）、名片、自定义、转发消息
- **消息历史**：分页加载（每页 40 条），支持同步后重新加载
- **输入状态**：防抖 1 秒后通知对方"正在输入"
- **已读回执**：标记可见的非语音消息为已读
- **失败处理**：检测被拉黑/删除好友、群解散/被移除等场景并插入提示消息
- **音视频通话**：通过 `PackageBridge.rtcBridge` 发起呼叫

子页面包括：聊天设置、群设置、群管理、群成员列表、群二维码、编辑群名。

#### 4.1.4 通讯录模块

[Contacts 页面](file:///home/bing/openim-flutter-demo/lib/pages/contacts) 包含：

- 好友列表 / 群组列表（A-Z 字母索引）
- 添加好友（搜索、扫码、申请验证）
- 创建群组（选择联系人 → 创建）
- 好友申请处理 / 群申请处理
- 用户资料面板 / 群资料面板

#### 4.1.5 核心控制器

| 控制器 | 文件 | 职责 |
|--------|------|------|
| `IMController` | [im_controller.dart](file:///home/bing/openim-flutter-demo/lib/core/controller/im_controller.dart) | SDK 初始化、登录登出、监听器注册、RTC 信令 |
| `AppController` | [app_controller.dart](file:///home/bing/openim-flutter-demo/lib/core/controller/app_controller.dart) | 通知、声音振动、应用角标、版本升级、设备信息 |
| `IMCallback` | [im_callback.dart](file:///home/bing/openim-flutter-demo/lib/core/im_callback.dart) | SDK 回调 → RxDart 流转换的事件总线 |
| `CacheController` | [cache_controller.dart](file:///home/bing/openim-flutter-demo/openim_common/lib/src/controller/cache_controller.dart) | Hive 存储通话记录 |
| `PushController` | [push_controller.dart](file:///home/bing/openim-flutter-demo/openim_common/lib/src/controller/push_controller.dart) | FCM 推送 Token 管理与消息处理 |

### 4.2 后端模块

#### 4.2.1 Python 业务服务

[Python 服务](file:///home/bing/openim-flutter-demo/backend/python-service/app/main.py) 提供以下路由模块：

| 模块 | 前缀 | 核心功能 |
|------|------|---------|
| 认证 (auth) | `/api/auth` | 发送验证码、注册、登录、登出 |
| 用户 (user) | `/api/user` | 资料查看/修改、改密、重置密码、黑名单、语言 |
| 会话 (conversation) | `/api/conversation` | 免打扰、置顶、删除、草稿、已读、列表 |
| 设置 (settings) | `/api/settings` | 字体大小、通知、勿扰、背景图 |
| 版本 (version) | `/api/version` | 客户端版本检查 |
| 多语言 (i18n) | `/api/i18n` | 多语言文本查询 |
| OpenIM 兼容层 | `/`（无前缀） | 模拟 OpenIM Chat Server API，使 Flutter SDK 无缝对接 |

**OpenIM 兼容层**是架构关键：它将响应格式从原生 `{code, msg, data}` 转换为 OpenIM 风格的 `{errCode, errMsg, errDlt, data}`，密码处理上对客户端发送的 MD5 密码再进行 bcrypt 哈希存储。

#### 4.2.2 Java 消息服务

[Java 服务](file:///home/bing/openim-flutter-demo/backend/java-service/src/main/java/com/openim) 提供：

- **WebSocket 网关**（`/ws`）：处理 `login`、`heartbeat`、`chat`、`pull_offline` 消息类型
- **消息 REST API**（`/api/message/`）：发送、转发、撤回、删除、清空、搜索、历史、离线
- **会话管理**：基于 `ConversationMember` 的成员关系管理
- **离线推送**：`OfflinePushService`（个推/Firebase/APNs 桩实现）

#### 4.2.3 文件服务

[文件服务](file:///home/bing/openim-flutter-demo/backend/file-service/app/routers/file.py) 提供：

| 接口 | 功能 |
|------|------|
| `POST /api/file/image/upload` | 聊天图片上传（原图 1280px + 缩略图 256px） |
| `POST /api/file/avatar/upload` | 头像上传（256x256 居中裁剪） |
| `POST /api/file/background/upload` | 背景图上传（最大 1920px） |
| `POST /api/file/file/upload` | 通用文件上传（限制 100MB） |
| `POST /api/file/release/upload` | 版本包上传（限制 200MB） |
| `GET /api/file/download` | 文件下载（流式响应） |
| `GET /api/file/presigned` | 生成预签名下载 URL |

---

## 5. 核心算法与实现

### 5.1 消息序列号生成算法

消息序列号（`seq`）通过 Redis 原子自增保证全局递增，每个会话独立计数：

```java
// MessageService.sendMessage()
String messageId = UUID.randomUUID().toString().replace("-", "");
Long seq = redisTemplate.opsForValue().increment("seq:" + conversationId);
```

**设计要点**：
- 使用 Redis `INCR` 原子操作，避免并发冲突
- `seq` 作为消息排序与历史分页游标的关键字段
- 消息表索引 `idx_conv_seq(conversation_id, seq)` 优化分页查询

### 5.2 消息分发算法

[MessageService.dispatchMessage](file:///home/bing/openim-flutter-demo/backend/java-service/src/main/java/com/openim/service/MessageService.java) 的分发逻辑：

```
对会话的每个活跃成员（排除发送者）:
  1. Redis HINCRBY unread:{memberId} {conversationId} 1  // 增加未读数
  2. Redis ZADD conv_list:{memberId} {timestamp} {conversationId}  // 更新会话排序
  3. IF 用户在线 (WsSessionManager.isOnline):
       → 推送 {type:"message", data:<Message>} 到所有 WS 会话
     ELSE IF 未开启免打扰:
       → OfflinePushService.pushOfflineMessage (离线推送)
```

### 5.3 消息历史分页算法

```java
// MessageRepository.findHistoryMessages (原生 SQL)
SELECT * FROM messages
WHERE conversation_id = ? AND status = 0 AND seq < ?
  AND (cleared_at IS NULL OR created_at > cleared_at)
ORDER BY seq DESC
LIMIT ?
```

**关键点**：
- 使用 `seq` 游标而非 OFFSET，避免深分页性能问题
- `cleared_at` 过滤已清空的历史消息
- `status = 0` 排除已撤回消息

### 5.4 图片压缩算法

[文件服务图片处理](file:///home/bing/openim-flutter-demo/backend/file-service/app/utils/image.py) 使用 Pillow：

```python
def compress_chat_image(data: bytes) -> tuple[bytes, bytes]:
    img = _open_image(data)  # EXIF 方向校正 + RGB 转换
    original = _encode(_resize_to_max(img, IMAGE_MAX_SIZE))      # 1280px
    thumbnail = _encode(_resize_to_max(img, THUMBNAIL_MAX_SIZE)) # 256px
    return original, thumbnail
```

- **聊天图片**：原图最大 1280px + 缩略图 256px，JPEG 质量 85
- **头像**：按短边缩放后居中裁剪为 256x256 正方形
- **背景图**：最大 1920px
- 使用 LANCZOS 重采样算法保证质量

### 5.5 客户端事件流转换算法

[IMCallback](file:///home/bing/openim-flutter-demo/lib/core/im_callback.dart) 将 SDK 回调转换为 RxDart 流：

```dart
// SDK 回调 → BehaviorSubject（保留最新值，支持多订阅）
final conversationChangedSubject = BehaviorSubject<List<ConversationInfo>>();

// SDK 回调 → PublishSubject（一次性事件）
final unreadMsgCountEventSubject = PublishSubject<int>();

// SDK 回调 → ReplaySubject（重放所有历史值）
final imSdkStatusSubject = ReplaySubject<...>();
```

**Subject 类型选择策略**：
- `BehaviorSubject`：需要订阅时获取最新值（如会话列表变更）
- `PublishSubject`：一次性事件（如未读数变化）
- `ReplaySubject`：需重放历史状态（如同步状态，新订阅者需知当前状态）

### 5.6 在线状态管理算法

```
用户登录 WS:
  → SET online:{userId} 1 EX 60  // 60秒 TTL
心跳 (每 < 60s):
  → EXPIRE online:{userId} 60    // 续期
断开连接 (无剩余会话):
  → DEL online:{userId}
```

多设备支持：`WsSessionManager` 使用 `ConcurrentHashMap<String, Set<WebSocketSession>>`，同一用户可有多条 WS 连接。

### 5.7 分布式锁算法

```java
// tryLock: SET NX EX
String token = UUID.randomUUID().toString();
Boolean locked = redisTemplate.opsForValue()
    .setIfAbsent("lock:" + resource, token, 10, TimeUnit.SECONDS);

// unlock: 校验 token 后删除（防止误删他人锁）
String current = redisTemplate.opsForValue().get("lock:" + resource);
if (token.equals(current)) {
    redisTemplate.delete("lock:" + resource);
}
```

---

## 6. API 接口规范

### 6.1 统一响应格式

#### 原生 API 响应格式（Python/Java 服务）

```json
{
  "code": 0,
  "msg": "ok",
  "data": { ... }
}
```

| code | 含义 |
|------|------|
| 0 | 成功 |
| 1 | 通用失败 |
| 400 | 参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

#### OpenIM 兼容层响应格式

```json
{
  "errCode": 0,
  "errMsg": "",
  "errDlt": "",
  "data": { ... }
}
```

### 6.2 认证机制

| 接口类型 | 认证方式 | Header |
|---------|---------|--------|
| 原生 `/api/*` | Bearer JWT | `Authorization: Bearer <token>` |
| OpenIM 兼容层 | Token Header | `token: <chatToken>` |
| WebSocket | Query 参数 | `ws://host/ws?token=<jwt>` |

**JWT Payload**：
```json
{
  "user_id": "uuid_hex",
  "account": "13800138000",
  "exp": 1782800000,
  "iat": 1782200000
}
```

### 6.3 Python 服务 API 清单

#### 认证接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/auth/send_code` | 否 | 发送验证码（开发模式固定 123456） |
| POST | `/api/auth/register` | 否 | 注册（验证码校验） |
| POST | `/api/auth/login` | 否 | 登录（账号或手机号 + 密码） |
| POST | `/api/auth/logout` | 是 | 登出（删除 Redis Token） |

#### 用户接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/user/profile` | 是 | 获取当前用户资料 |
| PUT | `/api/user/profile` | 是 | 更新资料（昵称/性别/生日/头像/邮箱） |
| PUT | `/api/user/password` | 是 | 修改密码 |
| POST | `/api/user/reset_password` | 是 | 通过手机号+验证码重置密码 |
| GET | `/api/user/blacklist` | 是 | 黑名单列表 |
| POST | `/api/user/blacklist/{user_id}` | 是 | 拉黑用户 |
| DELETE | `/api/user/blacklist/{user_id}` | 是 | 移除黑名单 |
| PUT | `/api/user/language` | 是 | 更新语言设置 |

#### 会话接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| PUT | `/api/conversation/{id}/mute` | 是 | 设置免打扰 |
| PUT | `/api/conversation/{id}/pin` | 是 | 设置置顶 |
| DELETE | `/api/conversation/{id}` | 是 | 删除会话（软删除） |
| PUT | `/api/conversation/{id}/draft` | 是 | 保存草稿 |
| GET | `/api/conversation/{id}/draft` | 是 | 读取草稿 |
| POST | `/api/conversation/mark_all_read` | 是 | 全部已读 |
| GET | `/api/conversation/list` | 是 | 会话列表（含未读数） |

#### 其他接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET/PUT | `/api/settings/` | 是 | 用户设置 |
| PUT | `/api/settings/background` | 是 | 设置聊天背景 |
| GET | `/api/version/check?platform=` | 否 | 版本检查 |
| GET | `/api/i18n/texts?lang=` | 否 | 多语言文本 |

#### OpenIM 兼容层接口（无 `/api` 前缀）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/account/code/send` | 发送验证码 |
| POST | `/account/code/verify` | 校验验证码 |
| POST | `/account/register` | 注册（返回 userID/imToken/chatToken） |
| POST | `/account/login` | 登录（密码或验证码） |
| POST | `/account/password/reset` | 重置密码 |
| POST | `/account/password/change` | 修改密码 |
| POST | `/user/update` | 更新用户信息 |
| POST | `/user/find/full` | 批量查询用户完整信息 |
| POST | `/user/search/full` | 搜索用户 |
| POST | `/user/rtc/get_token` | RTC Token（LiveKit 占位） |
| POST | `/friend/search` | 搜索好友 |
| POST | `/manager/get_users_online_status` | 查询在线状态 |
| POST | `/manager/get_all_users_uid` | 获取所有用户 ID |
| POST | `/third/minio_upload` | 文件上传代理 |
| POST | `/app/check` | 版本检查 |
| GET | `/client_config/get` | 客户端配置 |

### 6.4 Java 服务 API 清单

#### WebSocket 消息协议

客户端 → 服务端：

```json
{ "type": "login", "data": { "token": "<userId>" } }
{ "type": "heartbeat" }
{ "type": "chat", "data": { "conversation_id": "...", "msg_type": 1, "content": "..." } }
{ "type": "pull_offline" }
```

服务端 → 客户端：

```json
{ "type": "login_ack", "data": { "result": "success", "userId": "..." } }
{ "type": "pong", "data": { "timestamp": 1782200000 } }
{ "type": "chat_ack", "data": { "result": "success", "message_id": "...", "seq": 42 } }
{ "type": "message", "data": { <Message对象> } }
{ "type": "recall", "data": { "message_id": "...", "conversation_id": "...", "action": "recall" } }
{ "type": "pull_offline_ack", "data": { "messages": [...], "count": 10 } }
{ "type": "error", "data": { "message": "unknown type" } }
```

#### 消息 REST API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/message/send` | 发送消息 |
| POST | `/api/message/forward` | 转发消息 |
| POST | `/api/message/recall` | 撤回消息 |
| POST | `/api/message/delete` | 删除消息（本地） |
| POST | `/api/message/clear` | 清空会话 |
| GET | `/api/message/search?keyword=&user_id=` | 搜索消息 |
| GET | `/api/message/history?conversation_id=&user_id=&before_seq=&limit=` | 历史消息 |
| GET | `/api/message/offline?user_id=` | 离线消息 |

### 6.5 文件服务 API 清单

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/file/image/upload` | 聊天图片上传 |
| POST | `/api/file/avatar/upload` | 头像上传 |
| POST | `/api/file/background/upload` | 背景图上传 |
| POST | `/api/file/file/upload` | 通用文件上传 |
| POST | `/api/file/release/upload` | 版本包上传 |
| GET | `/api/file/download?bucket=&object_name=` | 文件下载 |
| GET | `/api/file/presigned?bucket=&object_name=&expires=3600` | 预签名 URL |

---

## 7. 数据流程设计

### 7.1 用户登录与认证流程

```
┌────────┐          ┌─────────┐         ┌────────┐         ┌─────────┐
│ Flutter │          │ Nginx   │         │ Python │         │  Redis  │
│ Client  │          │ (80/443)│         │ (8081) │         │  (6379) │
└───┬────┘          └────┬────┘         └───┬────┘         └────┬────┘
    │  POST /account/login │                  │                   │
    │  {phone, password}   │                  │                   │
    │─────────────────────►│                  │                   │
    │                      │  转发到 Python   │                   │
    │                      │─────────────────►│                   │
    │                      │                  │ 1.验证密码(bcrypt) │
    │                      │                  │ 2.生成JWT(7天)     │
    │                      │                  │ 3.SET token:{jwt}  │
    │                      │                  │──────────────────►│
    │                      │                  │ 4.更新last_login   │
    │                      │                  │   (MySQL)          │
    │                      │  {userID,        │                   │
    │                      │   imToken,       │                   │
    │                      │   chatToken}     │                   │
    │◄─────────────────────┤◄─────────────────┤                   │
    │                      │                  │                   │
    │ 存储LoginCertificate │                  │                   │
    │                      │                  │                   │
    │  WS连接 ws://host/ws?token=<jwt>        │                   │
    │─────────────────────►│                  │                   │
    │                      │ 转发到 Java:8082 │                   │
    │                      │──────────────────┼──────────────────►│
    │                      │                  │   Java Service    │
    │                      │                  │   SET online:{uid}│
    │  {type:"login"}      │                  │                   │
    │─────────────────────►│                  │                   │
    │  {type:"login_ack"}  │                  │                   │
    │◄─────────────────────┤                  │                   │
```

### 7.2 消息发送与分发流程

```
发送者                    Java Service              接收者(在线)         接收者(离线)
  │                          │                         │                    │
  │ WS: {type:"chat",       │                         │                    │
  │      data:{conv_id,     │                         │                    │
  │      msg_type, content}}│                         │                    │
  │────────────────────────►│                         │                    │
  │                          │                         │                    │
  │                 ┌────────┴────────┐               │                    │
  │                 │ 1.生成messageId │               │                    │
  │                 │ 2.INCR seq:{cid}│               │                    │
  │                 │ 3.保存MySQL     │               │                    │
  │                 │ 4.缓存Redis     │               │                    │
  │                 │   msg_cache:{cid}│              │                    │
  │                 │ 5.更新conv_list │               │                    │
  │                 │   (所有成员)    │               │                    │
  │                 └────────┬────────┘               │                    │
  │                          │                         │                    │
  │                 ┌────────┴────────┐               │                    │
  │                 │ dispatchMessage │               │                    │
  │                 │ (遍历活跃成员)  │               │                    │
  │                 └────────┬────────┘               │                    │
  │                          │                         │                    │
  │              ┌───────────┴───────────┐            │                    │
  │              │                       │            │                    │
  │              ▼                       ▼            │                    │
  │   HINCRBY unread:{uid}     检查在线状态           │                    │
  │              │                       │            │                    │
  │              │              在线?─────┼──是────────►│                    │
  │              │              │         │ WS推送     │                    │
  │              │              │         │{type:"message"}                 │
  │              │              │         │◄───────────┤                    │
  │              │              │         │            │                    │
  │              │              否        │            │                    │
  │              │              │         │            │                    │
  │              │              ▼         │            │                    │
  │              │     检查免打扰设置     │            │                    │
  │              │              │         │            │                    │
  │              │      未免打扰?─────────┼────────────┼───────────────────►│
  │              │              │         │            │ OfflinePushService │
  │              │              │         │            │ (个推/Firebase)    │
  │              │              │         │            │                    │
  │ WS: {type:"chat_ack",      │         │            │                    │
  │      data:{result,         │         │            │                    │
  │      message_id, seq}}     │         │            │                    │
  │◄───────────────────────────┤         │            │                    │
```

### 7.3 文件上传流程

```
Flutter Client          Python Service         File Service          MinIO
     │                       │                      │                  │
     │ POST /third/minio_upload                    │                  │
     │ (multipart, file)    │                      │                  │
     │──────────────────────►│                      │                  │
     │                       │ 判断文件类型         │                  │
     │                       │                      │                  │
     │                       │ 图片? POST /api/file/image/upload       │
     │                       │ 其他? POST /api/file/file/upload        │
     │                       │─────────────────────►│                  │
     │                       │                      │ Pillow压缩       │
     │                       │                      │ 生成object_name  │
     │                       │                      │ put_object       │
     │                       │                      │─────────────────►│
     │                       │                      │◄─────────────────│
     │                       │ {original_url,       │                  │
     │                       │  thumbnail_url}      │                  │
     │                       │◄─────────────────────┤                  │
     │ {errCode:0,          │                      │                  │
     │  data:{URL}}          │                      │                  │
     │◄──────────────────────┤                      │                  │
     │                       │                      │                  │
     │ URL嵌入消息内容       │                      │                  │
     │ WS发送图片消息        │                      │                  │
```

### 7.4 离线消息恢复流程

```
用户重新上线:
  1. WS login → 设置 online:{userId}
  2. WS {type:"pull_offline"} 
     → Java 返回最近 100 条跨会话消息
  3. 客户端按会话分组展示
  
  或 REST 分页拉取:
  GET /api/message/history?conversation_id=X&before_seq=Y&limit=50
     → Java 查询 status=0, seq<Y, created_at>cleared_at 的消息
     → 按 seq DESC 排序返回
```

### 7.5 客户端 SDK 事件流

```
OpenIM SDK 回调
       │
       ▼
IMController (注册监听器)
       │
       ▼
IMCallback mixin (回调 → RxDart Subject 转换)
       │
       ├──► conversationChangedSubject (BehaviorSubject)
       │         │
       │         ▼
       │    ConversationLogic.onChanged() → 更新 list.obs
       │         │
       │         ▼
       │    Obx(() => ListView) 重建
       │
       ├──► unreadMsgCountEventSubject (PublishSubject)
       │         │
       │         ▼
       │    HomeLogic → 更新角标 + AppController.showBadge()
       │
       └──► imSdkStatusSubject (ReplaySubject)
                 │
                 ▼
            ConversationLogic → 显示同步进度 UI
```

---

## 8. 关键代码解析

### 8.1 应用入口与初始化

[lib/main.dart](file:///home/bing/openim-flutter-demo/lib/main.dart)：

```dart
void main() {
  runZonedGuarded(() {
    FlutterError.onError = (FlutterErrorDetails details) {
      FlutterError.presentError(details);
      Logger.print('FlutterError: ${details.exception.toString()}, '
          '${details.stack.toString()}');
    };
    // Config.init 完成 SharedPreferences/Hive/MediaKit/HttpUtil 初始化后启动 App
    Config.init(() => runApp(const ChatApp()));
  }, (error, stackTrace) {
    Logger.print('FlutterError: ${error.toString()}, '
        '${stackTrace.toString()}', onlyConsole: true);
  });
}
```

**解析**：使用 `runZonedGuarded` 捕获异步错误，`FlutterError.onError` 捕获同步错误，形成完整的错误兜底。`Config.init` 是同步阻塞初始化（SP/Hive/网络库），完成后才 `runApp`。

### 8.2 全局控制器注入

[lib/app.dart](file:///home/bing/openim-flutter-demo/lib/app.dart)：

```dart
class InitBinding extends Bindings {
  @override
  void dependencies() {
    Get.put<IMController>(IMController());      // IM 核心，全局常驻
    Get.put<PushController>(PushController());   // 推送管理
    Get.put<CacheController>(CacheController()); // 本地缓存
  }
}
```

**解析**：`InitBinding` 作为 `initialBinding`，在 App 启动时立即注入三个全局控制器。`Get.put` 为非懒加载，控制器随 App 生命周期存活。页面级控制器使用 `Get.lazyPut` 在 `Bindings` 中按需创建。

### 8.3 SDK 初始化与监听器注册

[lib/core/controller/im_controller.dart](file:///home/bing/openim-flutter-demo/lib/core/controller/im_controller.dart)：

```dart
void initOpenIM() {
  OpenIM.iMManager.initSDK(
    platformID: Platform.isAndroid ? 2 : 1,
    apiAddr: Config.imApiUrl,    // HTTPS API 地址
    wsAddr: Config.imWsUrl,      // WSS WebSocket 地址
    dataDir: Config.cachePath,   // 本地数据库目录
    logLevel: Config.logLevel,
    onConnectListener: OnConnectListener(
      onConnectFailed: (_, _) => ...,
      onConnectSuccess: () => ...,
      onConnecting: () => ...,
    ),
  );
  // 注册六大监听器，回调路由到 IMCallback mixin 方法
  OpenIM.iMManager.userManager.setUserListener(...);
  OpenIM.iMManager.messageManager.setAdvancedMsgListener(...);
  OpenIM.iMManager.friendshipManager.setFriendshipListener(...);
  OpenIM.iMManager.conversationManager.setConversationListener(...);
  OpenIM.iMManager.groupManager.setGroupListener(...);
}
```

**解析**：SDK 初始化需要 `apiAddr`（REST API）和 `wsAddr`（WebSocket）两个地址。本项目通过 Nginx 反向代理统一入口，`Config` 根据 host 是否为 IP 自动选择 http/https 与 ws/wss 协议。

### 8.4 HTTP 请求封装

[openim_common/lib/src/utils/http_util.dart](file:///home/bing/openim-flutter-demo/openim_common/lib/src/utils/http_util.dart)：

```dart
static Future<dynamic> post(String path,
    {data, Options? options}) async {
  final operationID = DateTime.now().millisecondsSinceEpoch.toString();
  try {
    final response = await dio.post(path,
        data: data,
        options: (options ?? Options()).copyWith(
          headers: {'operationID': operationID},
        ));
    final resp = ApiResp.fromJson(response.data);
    if (resp.errCode == 0) {
      return resp.data;
    }
    IMViews.showToast(resp.errDlt);  // 业务错误提示
    return Future.error((resp.errCode, resp.errMsg));
  } on DioException catch (e) {
    return Future.error('接口：$path 信息：${e.message}');
  }
}
```

**解析**：
- `operationID` 使用时间戳生成，用于全链路日志追踪
- 响应统一解析为 `ApiResp`，`errCode == 0` 才返回 `data`
- 业务错误自动 Toast 提示并返回 `Future.error`，调用方可用 `try-catch` 或 `LoadingView.wrap` 处理
- `DioException` 转换为中文错误信息

### 8.5 消息发送与失败处理

[lib/pages/chat/chat_logic.dart](file:///home/bing/openim-flutter-demo/lib/pages/chat/chat_logic.dart)：

```dart
void _sendMessage(Message message) {
  OpenIM.iMManager.messageManager
      .sendMessage(
    message: message,
    offlinePushInfo: Config.offlinePushInfo,
  )
      .then(_sendSucceeded)
      .catchError((e) {
    if (e is PlatformException) {
      // 根据错误码插入本地提示消息
      switch (e.code) {
        case '13001': // 被拉黑
          _insertHintMessage(CustomMessageType.blockedByFriend);
          break;
        case '13002': // 被删除
          _insertHintMessage(CustomMessageType.deletedByFriend);
          break;
        // ... 群解散、被移除等
      }
    }
    _senFailed(e);
  });
}
```

**解析**：消息发送通过 SDK 的 `sendMessage`，返回 `Future<Message>`。失败时根据 `PlatformException` 错误码判断具体原因（如 13001 被拉黑），插入对应的本地提示消息（不发送到服务器），提升用户体验。

### 8.6 WebSocket 消息处理

[ChatWebSocketHandler.java](file:///home/bing/openim-flutter-demo/backend/java-service/src/main/java/com/openim/websocket/ChatWebSocketHandler.java)：

```java
@Override
protected void handleTextMessage(WebSocketSession session, TextMessage message) {
    WsMessage wsMsg = objectMapper.readValue(message.getPayload(), WsMessage.class);
    switch (wsMsg.getType()) {
        case "login":        handleLogin(session, wsMsg);    break;
        case "heartbeat":    handleHeartbeat(session);       break;
        case "chat":         handleChat(session, wsMsg);     break;
        case "pull_offline": handlePullOffline(session);     break;
        default: sendToSession(session, new WsMessage("error",
                Map.of("message", "unknown type")));
    }
}
```

**解析**：基于 `TextWebSocketHandler`，JSON 协议，`type` 字段路由到对应处理器。`login` 建立会话与用户绑定，`heartbeat` 续期在线状态，`chat` 处理消息发送，`pull_offline` 拉取离线消息。

### 8.7 OpenIM 兼容层密码处理

[openim_compat.py](file:///home/bing/openim-flutter-demo/backend/python-service/app/routers/openim_compat.py)：

```python
@router.post("/account/register")
async def register(req: dict):
    phone = req.get("phoneNumber", "")
    password = req.get("password")  # 客户端已 MD5
    # 对 MD5 后的密码再 bcrypt 哈希存储
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user_id = uuid.uuid4().hex
    await execute(
        "INSERT INTO users (user_id, account, password_hash, phone, ...) "
        "VALUES (%s, %s, %s, %s, ...)",
        (user_id, phone, password_hash.decode(), phone, ...)
    )
    token = create_access_token(user_id, phone)
    await redis.setex(f"token:{token}", JWT_EXPIRE_HOURS * 3600, user_id)
    return _ok({"userID": user_id, "imToken": token, "chatToken": token})
```

**解析**：客户端发送的密码已经是 MD5 哈希值（`IMUtils.generateMD5`），服务端对此 MD5 值再进行 bcrypt 哈希存储，实现双重保护。`imToken` 与 `chatToken` 使用同一个 JWT，简化客户端逻辑。

---

## 9. 数据库设计

### 9.1 ER 关系图

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    users     │     │   blacklist      │     │  user_settings  │
│──────────────│     │──────────────────│     │─────────────────│
│ id (PK)      │◄──┐ │ id (PK)          │  ┌──│ id (PK)         │
│ user_id (UQ) │   │ │ user_id          │  │  │ user_id (UQ)    │
│ account (UQ) │   │ │ blocked_user_id  │  │  │ font_size       │
│ phone (UQ)   │   │ │ created_at       │  │  │ notification    │
│ password_hash│   │ └──────────────────┘  │  │ vibration       │
│ avatar       │   │                       │  │ dnd_start/end   │
│ nickname     │   │   ┌──────────────────┐│  │ background_image│
│ gender       │   │   │     drafts       ││  └─────────────────┘
│ language     │   │   │──────────────────┘│
│ status       │   │   │ user_id          ││   ┌─────────────────┐
│ last_login_at│   │   │ conversation_id  ││   │  app_versions   │
└──────┬───────┘   │   │ content          ││   │─────────────────│
       │           │   └──────────────────┘│   │ platform        │
       │           │                       │   │ version         │
       │           │   ┌──────────────────┐│   │ version_code    │
       │           └───│ conv_members     ││   │ download_url    │
       │               │──────────────────┘│   │ is_force        │
       │               │ conversation_id  ││   └─────────────────┘
       │               │ user_id          ││
       │               │ is_pinned        ││   ┌─────────────────┐
       │               │ mute_notification││   │   i18n_texts    │
       │               │ unread_base      ││   │─────────────────│
       │               │ cleared_at       ││   │ lang            │
       │               │ is_deleted       ││   │ key_name        │
       │               └────────┬─────────┘│   │ value           │
       │                        │          │   └─────────────────┘
       │               ┌────────┴─────────┐│
       │               │  conversations   ││
       │               │──────────────────││
       │               │ conversation_id  ││
       │               │ type (1单聊/2群) ││
       │               │ last_message_id  ││
       │               │ last_message_time││
       │               └────────┬─────────┘│
       │                        │          │
       │               ┌────────┴─────────┐│
       └───────────────│    messages      ││
                       │──────────────────││
                       │ message_id (UQ)  ││
                       │ conversation_id  ││
                       │ sender_id        ││
                       │ msg_type         ││
                       │ content          ││
                       │ status (0/1/2)   ││
                       │ seq              ││
                       │ created_at(ms)   ││
                       └────────┬─────────┘│
                                │          │
                       ┌────────┴─────────┐│
                       │message_deletions ││
                       │──────────────────││
                       │ message_id       ││
                       │ user_id          ││
                       │ deleted_at       ││
                       └──────────────────┘│
```

### 9.2 表结构详解

#### users（用户表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED | 自增主键 |
| user_id | VARCHAR(64) | 业务用户 ID（UUID hex），唯一索引 |
| account | VARCHAR(64) | 登录账号，唯一索引 |
| password_hash | VARCHAR(128) | bcrypt 哈希 |
| phone | VARCHAR(20) | 手机号，唯一索引 |
| email | VARCHAR(128) | 邮箱 |
| avatar | VARCHAR(512) | 头像 URL（MinIO） |
| nickname | VARCHAR(64) | 昵称 |
| gender | TINYINT | 0未知/1男/2女 |
| birthday | DATE | 生日 |
| language | VARCHAR(16) | 语言，默认 zh-CN |
| status | TINYINT | 1正常/0禁用 |
| last_login_at | DATETIME | 最后登录时间 |

#### messages（消息表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT UNSIGNED | 自增主键 |
| message_id | VARCHAR(64) | 消息 ID（UUID），唯一索引 |
| conversation_id | VARCHAR(64) | 会话 ID |
| sender_id | VARCHAR(64) | 发送者 ID |
| msg_type | TINYINT | 1文本/2图片/3文件/4位置/5语音/6视频/99自定义 |
| content | TEXT | 消息内容（文本或 JSON） |
| status | TINYINT | 0正常/1已撤回/2已删除 |
| seq | BIGINT | 会话内递增序列号 |
| created_at | DATETIME(3) | 创建时间（毫秒精度） |

**索引**：`idx_conv_seq(conversation_id, seq)` 支持分页查询；`idx_conv_time(conversation_id, created_at)` 支持时间范围查询。

#### conversation_members（会话成员表）

| 字段 | 类型 | 说明 |
|------|------|------|
| conversation_id | VARCHAR(64) | 会话 ID |
| user_id | VARCHAR(64) | 用户 ID |
| is_pinned | TINYINT | 是否置顶 |
| mute_notification | TINYINT | 是否免打扰 |
| unread_base | INT | 未读计数基准 |
| cleared_at | DATETIME | 清空历史时间戳 |
| is_deleted | TINYINT | 软删除标记 |

### 9.3 Redis 键空间设计

| Key 模式 | 类型 | TTL | 用途 |
|---------|------|-----|------|
| `online:{user_id}` | String | 60s | 在线状态 |
| `unread:{user_id}` | Hash | - | 未读计数（field=conversation_id） |
| `conv_list:{user_id}` | ZSet | - | 会话列表（score=最后消息时间） |
| `msg_cache:{conversation_id}` | List | - | 消息缓存（保留最近 200 条） |
| `seq:{conversation_id}` | String | - | 消息序列号计数器 |
| `token:{token}` | String | 7天 | JWT Token（支持登出失效） |
| `vcode:{phone}` | String | 300s | 验证码 |
| `lock:{resource}` | String | 10s | 分布式锁 |

---

## 10. 开发环境配置指南

### 10.1 前置条件

| 软件 | 版本要求 | 说明 |
|------|---------|------|
| Flutter | 3.32.8 | [安装指南](https://docs.flutter.dev/get-started/install) |
| Dart | 3.0+ | 随 Flutter 安装 |
| Xcode | 16.1 | iOS 开发 |
| Android Studio | Koola 2024.1.1 Patch 1 | Android 开发 |
| JDK | 17 | Java 服务编译 |
| Python | 3.11+ | Python 服务运行 |
| Docker | 20.10+ | 后端服务编排 |
| Docker Compose | v2+ | 后端服务编排 |
| Git | 任意 | 版本控制 |

### 10.2 后端部署

#### 10.2.1 配置环境变量

编辑 [backend/.env](file:///home/bing/openim-flutter-demo/backend/.env)：

```bash
# MySQL
MYSQL_ROOT_PASSWORD=openim123        # 生产环境务必修改
MYSQL_DATABASE=openim
MYSQL_USER=openim
MYSQL_PASSWORD=openim123
MYSQL_PORT=3306

# Redis
REDIS_PASSWORD=openim123
REDIS_PORT=6379

# MinIO
MINIO_ROOT_USER=openim
MINIO_ROOT_PASSWORD=openim12345
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001

# 服务端口
PYTHON_SERVICE_PORT=8081
JAVA_SERVICE_PORT=8082
FILE_SERVICE_PORT=8083
NGINX_HTTP_PORT=80
NGINX_HTTPS_PORT=443

# JWT
PYTHON_JWT_SECRET=openim-jwt-secret-change-me  # 生产环境务必修改
PYTHON_JWT_EXPIRE_HOURS=168

# 容器间通信地址（使用容器名）
MYSQL_HOST=openim-mysql-service
REDIS_HOST=openim-redis-service
MINIO_HOST=openim-minio-service
MINIO_ENDPOINT=http://openim-minio-service:9000
PYTHON_SERVICE_HOST=openim-python-service
JAVA_SERVICE_HOST=openim-java-service
FILE_SERVICE_HOST=openim-file-service
```

#### 10.2.2 启动后端服务

```bash
cd backend

# 启动所有服务
docker compose --env-file .env up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f openim-python-service
docker compose logs -f openim-java-service

# 重建单个服务
docker compose --env-file .env up -d --build openim-python-service

# 停止所有服务
docker compose down

# 停止并清除数据卷（慎用）
docker compose down -v
```

#### 10.2.3 验证服务健康

```bash
# Python 服务
curl http://localhost:8081/health
# 期望: {"code":0,"msg":"ok","data":{"status":"healthy"}}

# 文件服务
curl http://localhost:8083/health

# Java 服务（通过 Nginx）
curl http://localhost/api/message/history
```

### 10.3 客户端配置

#### 10.3.1 修改服务器地址

编辑 [openim_common/lib/src/config.dart](file:///home/bing/openim-flutter-demo/openim_common/lib/src/config.dart)：

```dart
static const _host = "your-server-ip or your-domain";
```

- 若使用 IP 地址，自动使用 `http://` 和 `ws://`
- 若使用域名，自动使用 `https://` 和 `wss://`

#### 10.3.2 安装依赖与运行

```bash
# 清理并安装依赖
flutter clean
flutter pub get

# 运行（调试模式）
flutter run

# 指定设备运行
flutter run -d <device_id>

# 查看可用设备
flutter devices
```

#### 10.3.3 构建发布包

```bash
# Android APK
flutter build apk

# iOS IPA
flutter build ipa

# Android Release（不混淆，避免白屏）
flutter build apk --no-shrink
```

### 10.4 iOS 特殊配置

```bash
cd ios
rm -f Podfile.lock
rm -rf Pods
pod install
cd ..

# CPU 架构设置为 arm64
# 连接真机后 Archive
```

### 10.5 Android 模拟器配置

若需在模拟器运行，在 [android/build.gradle](file:///home/bing/openim-flutter-demo/android/build.gradle) 添加：

```gradle
ndk {
    abiFilters "armeabi-v7a", "x86"
}
```

### 10.6 代码混淆规则

若必须启用混淆，在 [android/app/proguard-rules.pro](file:///home/bing/openim-flutter-demo/android/app/proguard-rules.pro) 添加：

```
-keep class io.openim.**{*;}
-keep class open_im_sdk.**{*;}
-keep class open_im_sdk_callback.**{*;}
```

---

## 11. 使用示例

### 11.1 用户注册与登录示例

```dart
// 1. 发送验证码
await Apis.requestVerificationCode(
  phoneNumber: '13800138000',
  areaCode: '+86',
  usedFor: 1,  // 1=注册
);

// 2. 注册
final result = await Apis.register(
  phoneNumber: '13800138000',
  verificationCode: '123456',
  password: IMUtils.generateMD5('myPassword'),  // MD5 哈希
);
// result: {userID, imToken, chatToken}

// 3. 存储 LoginCertificate
DataSp.saveLoginCertificate(LoginCertificate(
  userID: result['userID'],
  imToken: result['imToken'],
  chatToken: result['chatToken'],
));

// 4. 登录 IM SDK
await imLogic.login(result['userID'], result['imToken']);
```

### 11.2 发送消息示例

```dart
// 发送文本消息
final message = await OpenIM.iMManager.messageManager.createTextMessage(
  text: 'Hello OpenIM!',
);
await OpenIM.iMManager.messageManager.sendMessage(
  message: message,
  receiverID: 'target_user_id',  // 单聊
  groupID: '',                    // 群聊时填写
  offlinePushInfo: Config.offlinePushInfo,
);

// 发送图片消息
final imageMsg = await OpenIM.iMManager.messageManager.createImageMessage(
  imagePath: file.path,
  onProgress: (progress) {
    print('上传进度: ${(progress * 100).toInt()}%');
  },
);
await OpenIM.iMManager.messageManager.sendMessage(
  message: imageMsg,
  receiverID: 'target_user_id',
  groupID: '',
);
```

### 11.3 监听会话变更示例

```dart
class ConversationLogic extends GetxController {
  final list = <ConversationInfo>[].obs;

  @override
  void onInit() {
    super.onInit();
    // 订阅会话变更流
    imLogic.conversationChangedSubject.listen((changed) {
      onChanged(changed);
    });
    imLogic.conversationAddedSubject.listen((added) {
      list.insertAll(0, added);
    });
  }

  void onChanged(List<ConversationInfo> changed) {
    for (var conv in changed) {
      final index = list.indexWhere(
        (e) => e.conversationID == conv.conversationID);
      if (index > -1) {
        list[index] = conv;
      } else {
        list.insert(0, conv);
      }
    }
    simpleSort();
  }
}
```

### 11.4 后端 API 调用示例

```bash
# 发送验证码
curl -X POST http://localhost/api/auth/send_code \
  -H "Content-Type: application/json" \
  -d '{"phone": "13800138000"}'

# 注册
curl -X POST http://localhost/account/register \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "13800138000", "password": "e10adc3949ba59abbe56e", "verifyCode": "123456"}'

# 登录
curl -X POST http://localhost/account/login \
  -H "Content-Type: application/json" \
  -d '{"phoneNumber": "13800138000", "password": "e10adc3949ba59abbe56e"}'

# 获取用户资料（需 Token）
curl http://localhost/api/user/profile \
  -H "Authorization: Bearer <jwt_token>"

# 上传文件
curl -X POST http://localhost:8083/api/file/image/upload \
  -F "file=@/path/to/image.jpg"
```

### 11.5 WebSocket 连接示例

```javascript
// JavaScript 示例
const ws = new WebSocket('ws://localhost/ws?token=<jwt_token>');

ws.onopen = () => {
  ws.send(JSON.stringify({ type: 'login', data: { token: '<user_id>' } }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  switch (msg.type) {
    case 'login_ack':
      console.log('登录成功', msg.data.userId);
      // 发送心跳
      setInterval(() => {
        ws.send(JSON.stringify({ type: 'heartbeat' }));
      }, 30000);
      break;
    case 'message':
      console.log('收到消息', msg.data);
      break;
    case 'pong':
      console.log('心跳响应', msg.data.timestamp);
      break;
  }
};

// 发送消息
ws.send(JSON.stringify({
  type: 'chat',
  data: {
    conversation_id: 'conv_123',
    msg_type: 1,
    content: 'Hello from WebSocket!'
  }
}));
```

---

## 12. 代码注释规范

### 12.1 Dart 代码注释规范

#### 文件头注释

```dart
/// 文件描述：简要说明文件职责与核心功能。
///
/// 作者：作者名
/// 创建日期：YYYY-MM-DD
/// 修改记录：
///   - YYYY-MM-DD 作者 修改内容描述
```

#### 类注释

```dart
/// 控制器/组件描述。
///
/// 详细说明类的职责、核心逻辑、依赖关系。
///
/// 示例：
/// ```
/// final controller = Get.find<ChatLogic>();
/// controller.sendTextMsg('Hello');
/// ```
class ChatLogic extends GetxController {
  /// 发送文本消息。
  ///
  /// [text] 消息文本内容
  /// [receiverID] 接收者用户 ID（单聊）
  /// [groupID] 群组 ID（群聊）
  ///
  /// 返回发送结果，失败时抛出 [PlatformException]。
  Future<void> sendTextMsg(String text, {String? receiverID, String? groupID}) {
    // ...
  }
}
```

#### 行内注释

```dart
// 使用 BehaviorSubject 保留最新值，新订阅者可立即获取当前状态
final conversationChangedSubject = BehaviorSubject<List<ConversationInfo>>();

// TODO: 待实现的功能描述
// FIXME: 已知问题描述
// HACK: 临时方案描述，需后续优化
// NOTE: 特别注意事项
```

### 12.2 Python 代码注释规范

```python
"""模块描述：简要说明模块职责。

详细描述模块的功能、依赖关系、使用方式。
"""

def send_message(conversation_id: str, sender_id: str, content: str) -> dict:
    """发送消息到指定会话。

    Args:
        conversation_id: 会话 ID
        sender_id: 发送者用户 ID
        content: 消息内容

    Returns:
        包含 message_id 和 seq 的字典

    Raises:
        ValueError: 当会话不存在时
    """
    # 生成唯一消息 ID
    message_id = uuid.uuid4().hex
    # Redis 原子自增生成序列号
    seq = await redis.incr(f"seq:{conversation_id}")
    ...
```

### 12.3 Java 代码注释规范

```java
/**
 * 消息服务，负责消息的发送、分发、撤回等核心业务。
 *
 * <p>使用 Redis 实现消息序列号生成与在线状态管理，
 * 通过 WebSocket 推送实时消息给在线用户。
 *
 * @author openim
 * @since 1.0.0
 */
@Service
public class MessageService {

    /**
     * 发送消息到指定会话。
     *
     * @param conversationId 会话 ID
     * @param senderId       发送者用户 ID
     * @param msgType        消息类型（1=文本, 2=图片, ...）
     * @param content        消息内容
     * @return 保存后的消息对象
     */
    @Transactional
    public Message sendMessage(String conversationId, String senderId,
                               int msgType, String content) {
        // ...
    }
}
```

### 12.4 SQL 注释规范

```sql
-- 创建消息表
CREATE TABLE messages (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    message_id VARCHAR(64) NOT NULL COMMENT '消息唯一ID(UUID)',
    conversation_id VARCHAR(64) NOT NULL COMMENT '会话ID',
    sender_id VARCHAR(64) NOT NULL COMMENT '发送者用户ID',
    msg_type TINYINT NOT NULL COMMENT '消息类型: 1文本 2图片 3文件 4位置 5语音 6视频',
    content TEXT COMMENT '消息内容(文本或JSON)',
    status TINYINT DEFAULT 0 COMMENT '状态: 0正常 1已撤回 2已删除',
    seq BIGINT NOT NULL COMMENT '会话内递增序列号',
    created_at DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间(毫秒)',
    UNIQUE KEY uk_message_id (message_id),
    KEY idx_conv_seq (conversation_id, seq)  -- 分页查询索引
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='聊天消息表';
```

---

## 13. 文档维护与更新机制

### 13.1 文档版本管理

- 文档与代码同仓库管理，位于项目根目录
- 文档版本号与项目版本号保持同步
- 每次重大更新需在文件头更新版本号与最后更新日期

### 13.2 更新触发条件

| 触发场景 | 更新内容 | 负责角色 |
|---------|---------|---------|
| 新增功能模块 | 功能模块说明、API 接口、数据流程 | 开发者 |
| API 变更 | API 接口规范、使用示例 | 后端开发 |
| 数据库变更 | 数据库设计、ER 图 | 后端开发 |
| 架构调整 | 架构概述、技术选型、流程图 | 架构师 |
| 依赖升级 | 开发环境配置、技术选型 | 全体开发 |

### 13.3 维护流程

1. **提交变更**：代码 PR 中包含文档更新部分
2. **代码审查**：审查者同步审查文档准确性
3. **合并发布**：文档随代码合并至主分支
4. **定期审查**：每季度进行一次文档全面审查，确保与代码一致

### 13.4 文档规范要点

- **图表优先**：复杂逻辑优先使用 ASCII 图表或 Mermaid 图表
- **代码引用**：引用代码文件时使用相对路径，便于定位
- **示例可运行**：所有使用示例需确保可实际运行
- **中英术语统一**：技术术语保持中英对照一致性
- **避免冗余**：避免重复 README 中已有内容，聚焦技术细节

---

## 附录

### A. 项目目录结构

```
openim-flutter-demo/
├── android/                    # Android 原生配置
├── ios/                        # iOS 原生配置
├── lib/                        # Flutter 应用代码
│   ├── core/                   # 核心控制器与回调
│   ├── pages/                  # 页面（View/Logic/Binding）
│   ├── routes/                 # 路由配置
│   ├── widgets/                # 应用级组件
│   ├── app.dart                # App 入口
│   └── main.dart               # main 函数
├── openim_common/              # 内部共享包
│   ├── lib/src/
│   │   ├── bridge/             # 包桥接
│   │   ├── controller/         # 缓存/推送控制器
│   │   ├── extension/          # 扩展方法
│   │   ├── models/             # 数据模型
│   │   ├── res/                # 资源（图片/字符串/样式/语言）
│   │   ├── utils/              # 工具类（HTTP/SP/日志等）
│   │   ├── widgets/            # UI 组件库
│   │   ├── apis.dart           # API 封装
│   │   ├── config.dart         # 配置
│   │   └── urls.dart           # URL 定义
│   └── assets/                 # 静态资源
├── local_plugin/               # 本地插件（音视频呼叫弹窗）
├── backend/                    # 后端服务
│   ├── python-service/         # Python 业务服务
│   ├── java-service/           # Java 消息服务
│   ├── file-service/           # 文件服务
│   ├── mysql/                  # MySQL 配置与初始化
│   ├── redis/                  # Redis 配置
│   ├── nginx/                  # Nginx 配置
│   ├── docker-compose.yml      # 服务编排
│   ├── .env                    # 环境变量
│   └── .env.example            # 环境变量示例
├── launcher_icon/              # 应用图标
├── firebase.json               # Firebase 配置
├── flutter_launcher_icons.yaml # 图标生成配置
├── flutter_native_splash.yaml  # 启动屏配置
└── analysis_options.yaml       # Dart 分析规则
```

### B. 关键端口速查

| 服务 | 端口 | 协议 |
|------|------|------|
| Nginx HTTP | 80 | HTTP |
| Nginx HTTPS | 443 | HTTPS |
| Python Service | 8081 | HTTP |
| Java Service | 8082 | HTTP/WS |
| File Service | 8083 | HTTP |
| MySQL | 3306 | TCP |
| Redis | 6379 | TCP |
| MinIO API | 9000 | HTTP |
| MinIO Console | 9001 | HTTP |

### C. 常见问题排查

| 问题 | 排查方向 |
|------|---------|
| 客户端无法连接 | 检查 `Config._host` 配置、Nginx 是否运行、防火墙端口 |
| WebSocket 断开 | 检查 Nginx `/ws` 代理配置、`proxy_read_timeout` |
| 消息发送失败 | 检查 Java 服务日志、MySQL 连接、Redis 连接 |
| 图片上传失败 | 检查 MinIO 服务状态、文件服务日志、bucket 是否存在 |
| 验证码不生效 | 开发模式固定 123456，检查 Redis `vcode:{phone}` |
| 离线推送不工作 | `OfflinePushService` 为桩实现，需集成实际 SDK |
| Release 白屏 | 使用 `flutter build apk --no-shrink` 或关闭混淆 |

---

> **文档结束** | 如有疑问请参阅 [OpenIM 官方文档](https://docs.openim.io/) 或加入社区交流。
