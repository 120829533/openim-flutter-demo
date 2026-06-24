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
 * 会话成员实体（对应 conversation_members 表）
 * is_pinned: 0=未置顶 1=置顶
 * mute_notification: 0=正常 1=免打扰
 * is_deleted: 0=正常 1=已退出
 */
@Data
@Entity
@Table(name = "conversation_members")
public class ConversationMember {

    /** 自增主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id")
    private Long id;

    /** 会话 ID */
    @Column(name = "conversation_id", nullable = false, length = 64)
    private String conversationId;

    /** 用户 ID */
    @Column(name = "user_id", nullable = false, length = 64)
    private String userId;

    /** 是否置顶：0=否 1=是 */
    @Column(name = "is_pinned", nullable = false)
    private Integer isPinned;

    /** 是否免打扰：0=否 1=是 */
    @Column(name = "mute_notification", nullable = false)
    private Integer muteNotification;

    /** 未读计数基准（用于增量计算） */
    @Column(name = "unread_base")
    private Integer unreadBase;

    /** 清空时间（清空会话时记录，历史消息只查此时间之后的） */
    @Column(name = "cleared_at")
    private LocalDateTime clearedAt;

    /** 是否已删除：0=否 1=是 */
    @Column(name = "is_deleted", nullable = false)
    private Integer isDeleted;

    /** 加入时间 */
    @Column(name = "joined_at")
    private LocalDateTime joinedAt;

    /** 更新时间 */
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}
