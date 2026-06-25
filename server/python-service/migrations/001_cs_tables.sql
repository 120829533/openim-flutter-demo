-- 客服系统表结构
-- 运行：mysql -u root -p < server/python-service/migrations/001_cs_tables.sql

USE openim;

-- 客服访客表
CREATE TABLE IF NOT EXISTS cs_visitors (
    visitor_id VARCHAR(32) PRIMARY KEY COMMENT '访客唯一 ID',
    visitor_name VARCHAR(100) NOT NULL DEFAULT '' COMMENT '访客昵称',
    visitor_avatar VARCHAR(500) NOT NULL DEFAULT '' COMMENT '访客头像 URL',
    visitor_ip VARCHAR(45) DEFAULT NULL COMMENT '访客 IP',
    source_page VARCHAR(500) DEFAULT NULL COMMENT '来源页面',
    first_seen DATETIME NOT NULL COMMENT '首次访问时间',
    last_seen DATETIME NOT NULL COMMENT '最后访问时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_ip (visitor_ip),
    INDEX idx_last_seen (last_seen)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客服访客表';

-- 客服会话表
CREATE TABLE IF NOT EXISTS cs_conversations (
    conversation_id VARCHAR(32) PRIMARY KEY COMMENT '会话唯一 ID',
    visitor_id VARCHAR(32) NOT NULL COMMENT '访客 ID',
    cs_user_id VARCHAR(32) NOT NULL DEFAULT 'cs_agent_001' COMMENT '客服 ID',
    status ENUM('active', 'closed', 'transferred') NOT NULL DEFAULT 'active' COMMENT '会话状态',
    last_message TEXT DEFAULT NULL COMMENT '最后一条消息',
    last_message_time DATETIME DEFAULT NULL COMMENT '最后消息时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_visitor (visitor_id),
    INDEX idx_cs_user (cs_user_id),
    INDEX idx_status (status),
    INDEX idx_last_time (last_message_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客服会话表';

-- 客服消息表
CREATE TABLE IF NOT EXISTS cs_messages (
    message_id VARCHAR(64) PRIMARY KEY COMMENT '消息唯一 ID',
    conversation_id VARCHAR(32) NOT NULL COMMENT '会话 ID',
    visitor_id VARCHAR(32) NOT NULL COMMENT '访客 ID',
    cs_user_id VARCHAR(32) NOT NULL COMMENT '客服 ID',
    content TEXT NOT NULL COMMENT '消息内容',
    msg_type TINYINT NOT NULL DEFAULT 1 COMMENT '消息类型：1=文本',
    direction ENUM('visitor', 'agent') NOT NULL COMMENT '消息方向',
    is_read TINYINT NOT NULL DEFAULT 0 COMMENT '是否已读',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conv (conversation_id),
    INDEX idx_visitor (visitor_id),
    INDEX idx_direction_read (direction, is_read),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客服消息表';

-- 插入预设客服账号（用于 APK 客服端登录）
INSERT IGNORE INTO users (user_id, account, password_hash, phone, email, avatar, nickname,
                          gender, birthday, language, status, last_login_at, created_at, updated_at)
VALUES ('cs_agent_001', 'cs_agent_001', '', '', '', '', '客服-云娜法兰',
        0, NULL, 'zh-CN', 1, NULL, NOW(), NOW());

-- 为客服账号创建默认设置
INSERT IGNORE INTO user_settings
    (user_id, font_size, notification_sound, vibration, dnd_start, dnd_end,
     background_image, created_at, updated_at)
VALUES ('cs_agent_001', 2, 1, 1, NULL, NULL, '', NOW(), NOW());
