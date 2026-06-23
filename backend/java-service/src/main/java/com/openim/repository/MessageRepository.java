package com.openim.repository;

import com.openim.model.Message;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 消息 Repository
 */
@Repository
public interface MessageRepository extends JpaRepository<Message, Long> {

    /** 根据 messageId 查询 */
    Message findByMessageId(String messageId);

    /**
     * 历史消息漫游：查询某会话中 seq < before_seq 且在 cleared_at 之后的消息
     * 按 seq 倒序，取 limit 条
     */
    @Query(value = "SELECT * FROM messages m " +
            "WHERE m.conversation_id = :conversationId " +
            "AND m.status = 0 " +
            "AND m.seq < :beforeSeq " +
            "AND (:clearedAt IS NULL OR m.created_at > :clearedAt) " +
            "ORDER BY m.seq DESC " +
            "LIMIT :limit",
            nativeQuery = true)
    List<Message> findHistoryMessages(@Param("conversationId") String conversationId,
                                      @Param("beforeSeq") Long beforeSeq,
                                      @Param("clearedAt") LocalDateTime clearedAt,
                                      @Param("limit") int limit);

    /**
     * 全局关键词检索（按用户参与的会话过滤）
     * 简化版：直接按 content LIKE 检索
     */
    @Query(value = "SELECT * FROM messages m " +
            "WHERE m.status = 0 " +
            "AND m.content LIKE CONCAT('%', :keyword, '%') " +
            "AND m.conversation_id IN (" +
            "   SELECT cm.conversation_id FROM conversation_members cm WHERE cm.user_id = :userId AND cm.is_deleted = 0" +
            ") " +
            "ORDER BY m.created_at DESC " +
            "LIMIT 200",
            nativeQuery = true)
    List<Message> searchByKeyword(@Param("keyword") String keyword,
                                  @Param("userId") String userId);

    /**
     * 拉取离线消息：查询用户所有会话中最近未读消息
     * 取最近 100 条
     */
    @Query(value = "SELECT * FROM messages m " +
            "WHERE m.status = 0 " +
            "AND m.conversation_id IN (" +
            "   SELECT cm.conversation_id FROM conversation_members cm WHERE cm.user_id = :userId AND cm.is_deleted = 0" +
            ") " +
            "AND (:lastLoginAt IS NULL OR m.created_at > :lastLoginAt) " +
            "ORDER BY m.created_at DESC " +
            "LIMIT 100",
            nativeQuery = true)
    List<Message> findOfflineMessages(@Param("userId") String userId,
                                      @Param("lastLoginAt") LocalDateTime lastLoginAt);

    /**
     * 撤回消息：更新 status = 1
     */
    @Modifying
    @Query(value = "UPDATE messages SET status = 1 WHERE message_id = :messageId",
            nativeQuery = true)
    int recallMessage(@Param("messageId") String messageId);

    /**
     * 本地单条删除：写入 message_deletions 表
     */
    @Modifying
    @Query(value = "INSERT INTO message_deletions (message_id, user_id, created_at) " +
            "VALUES (:messageId, :userId, NOW()) " +
            "ON DUPLICATE KEY UPDATE created_at = NOW()",
            nativeQuery = true)
    int markMessageDeleted(@Param("messageId") String messageId,
                           @Param("userId") String userId);

    /**
     * 查询会话内最新消息（用于更新会话 last_message）
     */
    @Query(value = "SELECT * FROM messages m " +
            "WHERE m.conversation_id = :conversationId " +
            "ORDER BY m.seq DESC LIMIT 1",
            nativeQuery = true)
    Message findLatestByConversation(@Param("conversationId") String conversationId);

    /**
     * 查询会话内消息总数
     */
    long countByConversationId(String conversationId);
}
