-- ============================================================
-- OpenIM 后端数据库初始化脚本
-- 容器：openim-mysql-service
-- 字符集：utf8mb4
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 1. 用户表：账号、密码哈希、手机号、邮箱、头像、昵称、性别、生日、语言偏好
-- ============================================================
CREATE TABLE IF NOT EXISTS `users` (
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`            VARCHAR(64)  NOT NULL COMMENT '用户唯一ID（业务层生成）',
  `account`            VARCHAR(64)  NOT NULL COMMENT '登录账号',
  `password_hash`      VARCHAR(128) NOT NULL COMMENT '密码哈希（bcrypt）',
  `phone`              VARCHAR(20)  NOT NULL DEFAULT '' COMMENT '手机号',
  `email`              VARCHAR(128) NOT NULL DEFAULT '' COMMENT '邮箱',
  `avatar`             VARCHAR(512) NOT NULL DEFAULT '' COMMENT '头像URL（MinIO）',
  `nickname`           VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '昵称',
  `gender`             TINYINT      NOT NULL DEFAULT 0 COMMENT '性别 0未知 1男 2女',
  `birthday`           DATE         DEFAULT NULL COMMENT '生日',
  `language`           VARCHAR(16)  NOT NULL DEFAULT 'zh-CN' COMMENT '语言偏好',
  `status`             TINYINT      NOT NULL DEFAULT 1 COMMENT '账号状态 1正常 0禁用',
  `last_login_at`      DATETIME     DEFAULT NULL COMMENT '最后登录时间',
  `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_id` (`user_id`),
  UNIQUE KEY `uk_account` (`account`),
  UNIQUE KEY `uk_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- ============================================================
-- 2. 黑名单关系表
-- ============================================================
CREATE TABLE IF NOT EXISTS `blacklist` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id`         VARCHAR(64)  NOT NULL COMMENT '拉黑发起者',
  `blocked_user_id` VARCHAR(64)  NOT NULL COMMENT '被拉黑用户',
  `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_blocked` (`user_id`, `blocked_user_id`),
  KEY `idx_blocked` (`blocked_user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='黑名单关系表';

-- ============================================================
-- 3. 会话表：会话ID、类型、最后消息时间
-- ============================================================
CREATE TABLE IF NOT EXISTS `conversations` (
  `id`               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `conversation_id`  VARCHAR(64)  NOT NULL COMMENT '会话唯一ID',
  `type`             TINYINT      NOT NULL DEFAULT 1 COMMENT '会话类型 1单聊 2群聊',
  `last_message_id`  VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '最后消息ID',
  `last_message_time` DATETIME    DEFAULT NULL COMMENT '最后消息时间',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conversation_id` (`conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话表';

-- ============================================================
-- 4. 会话成员表：参与者、置顶状态、免打扰开关、未读计数基准、清空时间
-- ============================================================
CREATE TABLE IF NOT EXISTS `conversation_members` (
  `id`               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `conversation_id`  VARCHAR(64)  NOT NULL COMMENT '会话ID',
  `user_id`          VARCHAR(64)  NOT NULL COMMENT '参与者用户ID',
  `is_pinned`        TINYINT      NOT NULL DEFAULT 0 COMMENT '是否置顶 0否 1是',
  `mute_notification` TINYINT     NOT NULL DEFAULT 0 COMMENT '是否免打扰 0否 1是',
  `unread_base`      INT          NOT NULL DEFAULT 0 COMMENT '未读计数基准（已读位点）',
  `cleared_at`       DATETIME     DEFAULT NULL COMMENT '清空会话记录时间点',
  `is_deleted`       TINYINT      NOT NULL DEFAULT 0 COMMENT '是否已删除该会话 0否 1是',
  `joined_at`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conv_user` (`conversation_id`, `user_id`),
  KEY `idx_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话成员表';

-- ============================================================
-- 5. 消息表：消息ID、会话ID、发送者、消息类型、内容、状态、创建时间
-- ============================================================
CREATE TABLE IF NOT EXISTS `messages` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `message_id`      VARCHAR(64)  NOT NULL COMMENT '消息唯一ID',
  `conversation_id` VARCHAR(64)  NOT NULL COMMENT '会话ID',
  `sender_id`       VARCHAR(64)  NOT NULL COMMENT '发送者用户ID',
  `msg_type`        TINYINT      NOT NULL DEFAULT 1 COMMENT '消息类型 1文本 2图片 3文件 4位置 5语音 6视频 99自定义',
  `content`         TEXT         COMMENT '消息内容（文本/JSON元数据）',
  `status`          TINYINT      NOT NULL DEFAULT 0 COMMENT '状态 0正常 1已撤回 2已删除',
  `seq`             BIGINT       NOT NULL DEFAULT 0 COMMENT '消息序号（会话内递增）',
  `created_at`      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_message_id` (`message_id`),
  KEY `idx_conv_seq` (`conversation_id`, `seq`),
  KEY `idx_conv_time` (`conversation_id`, `created_at`),
  KEY `idx_sender` (`sender_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息表';

-- ============================================================
-- 6. 消息单条删除标记表（用户维度本地删除）
-- ============================================================
CREATE TABLE IF NOT EXISTS `message_deletions` (
  `id`          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `message_id`  VARCHAR(64)  NOT NULL COMMENT '消息ID',
  `user_id`     VARCHAR(64)  NOT NULL COMMENT '删除该消息的用户',
  `deleted_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_msg_user` (`message_id`, `user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='消息单条删除标记表';

-- ============================================================
-- 7. 草稿表：用户-会话维度的草稿内容
-- ============================================================
CREATE TABLE IF NOT EXISTS `drafts` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id`         VARCHAR(64)  NOT NULL COMMENT '用户ID',
  `conversation_id` VARCHAR(64)  NOT NULL COMMENT '会话ID',
  `content`         TEXT         COMMENT '草稿内容',
  `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_conv` (`user_id`, `conversation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='聊天草稿表';

-- ============================================================
-- 8. 用户设置表：字体大小、通知偏好、背景图片路径
-- ============================================================
CREATE TABLE IF NOT EXISTS `user_settings` (
  `id`                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id`            VARCHAR(64)  NOT NULL COMMENT '用户ID',
  `font_size`          TINYINT      NOT NULL DEFAULT 2 COMMENT '字体大小 1小 2标准 3大 4超大',
  `notification_sound` TINYINT      NOT NULL DEFAULT 1 COMMENT '提示音 0关 1开',
  `vibration`          TINYINT      NOT NULL DEFAULT 1 COMMENT '震动 0关 1开',
  `dnd_start`          TIME         DEFAULT NULL COMMENT '免打扰开始时段',
  `dnd_end`            TIME         DEFAULT NULL COMMENT '免打扰结束时段',
  `background_image`   VARCHAR(512) NOT NULL DEFAULT '' COMMENT '聊天背景图URL（MinIO）',
  `created_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户设置表';

-- ============================================================
-- 9. 客户端版本更新记录表
-- ============================================================
CREATE TABLE IF NOT EXISTS `app_versions` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform`      VARCHAR(16)  NOT NULL DEFAULT 'android' COMMENT '平台 android/ios',
  `version`       VARCHAR(32)  NOT NULL COMMENT '版本号 如 1.2.0',
  `version_code`  INT          NOT NULL COMMENT '版本序号（数字递增）',
  `download_url`  VARCHAR(512) NOT NULL DEFAULT '' COMMENT '下载地址（MinIO）',
  `update_log`    TEXT         COMMENT '更新日志',
  `is_force`      TINYINT      NOT NULL DEFAULT 0 COMMENT '是否强制更新 0否 1是',
  `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_platform_code` (`platform`, `version_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户端版本记录表';

-- ============================================================
-- 10. 多语言文案表
-- ============================================================
CREATE TABLE IF NOT EXISTS `i18n_texts` (
  `id`         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `lang`       VARCHAR(16)  NOT NULL COMMENT '语言 如 zh-CN en',
  `key_name`   VARCHAR(128) NOT NULL COMMENT '文案键',
  `value`      TEXT         NOT NULL COMMENT '文案值',
  `updated_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_lang_key` (`lang`, `key_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='多语言文案表';

-- ============================================================
-- 初始数据：多语言文案示例
-- ============================================================
INSERT INTO `i18n_texts` (`lang`, `key_name`, `value`) VALUES
  ('zh-CN', 'app_name',        'OpenIM'),
  ('zh-CN', 'login',           '登录'),
  ('zh-CN', 'register',        '注册'),
  ('zh-CN', 'send_message',    '发送消息'),
  ('zh-CN', 'message_recalled','消息已撤回'),
  ('en',    'app_name',        'OpenIM'),
  ('en',    'login',           'Login'),
  ('en',    'register',        'Register'),
  ('en',    'send_message',    'Send Message'),
  ('en',    'message_recalled','Message recalled');

-- 初始版本记录示例
INSERT INTO `app_versions` (`platform`, `version`, `version_code`, `download_url`, `update_log`, `is_force`) VALUES
  ('android', '1.0.0', 1, '', '首次发布', 0),
  ('ios',     '1.0.0', 1, '', '首次发布', 0);

SET FOREIGN_KEY_CHECKS = 1;
