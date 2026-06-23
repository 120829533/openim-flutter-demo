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
 * 消息实体（对应 messages 表）
 * status: 0=正常, 1=已撤回
 * msg_type: 1=文本, 2=图片, 3=语音, 4=视频, 5=文件, 100=系统消息
 */
@Data
@Entity
@Table(name = "messages")
public class Message {

    /** 自增主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    /** 业务消息 ID（UUID） */
    @Column(name = "message_id", nullable = false, length = 64, unique = true)
    private String messageId;

    /** 会话 ID */
    @Column(name = "conversation_id", nullable = false, length = 64)
    private String conversationId;

    /** 发送者用户 ID */
    @Column(name = "sender_id", nullable = false, length = 64)
    private String senderId;

    /** 消息类型：1=文本 2=图片 3=语音 4=视频 5=文件 100=系统 */
    @Column(name = "msg_type", nullable = false)
    private Integer msgType;

    /** 消息内容（文本/JSON） */
    @Column(name = "content", columnDefinition = "TEXT")
    private String content;

    /** 消息状态：0=正常 1=已撤回 */
    @Column(name = "status", nullable = false)
    private Integer status;

    /** 会话内单调递增序列号 */
    @Column(name = "seq")
    private Long seq;

    /** 创建时间 */
    @Column(name = "created_at")
    private LocalDateTime createdAt;
}
