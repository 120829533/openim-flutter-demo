package com.openim.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 会话实体（对应 conversations 表）
 * type: 1=单聊, 2=群聊
 */
@Data
@Entity
@Table(name = "conversations")
public class Conversation {

    /** 自增主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    /** 会话 ID */
    @Column(name = "conversation_id", nullable = false, length = 64, unique = true)
    private String conversationId;

    /** 会话类型：1=单聊 2=群聊 */
    @Column(name = "type", nullable = false)
    private Integer type;

    /** 最新消息 ID */
    @Column(name = "last_message_id", length = 64)
    private String lastMessageId;

    /** 最新消息时间 */
    @Column(name = "last_message_time")
    private LocalDateTime lastMessageTime;

    /** 创建时间 */
    @Column(name = "created_at")
    private LocalDateTime createdAt;

    /** 更新时间 */
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
