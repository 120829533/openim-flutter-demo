package com.openim.repository;

import com.openim.model.ConversationMember;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/**
 * 会话成员 Repository
 */
@Repository
public interface ConversationMemberRepository extends JpaRepository<ConversationMember, Long> {

    /** 查询会话内所有未删除成员 */
    @Query("SELECT cm FROM ConversationMember cm WHERE cm.conversationId = :conversationId AND cm.isDeleted = 0")
    List<ConversationMember> findActiveMembers(@Param("conversationId") String conversationId);

    /** 查询用户在某会话中的成员记录 */
    @Query("SELECT cm FROM ConversationMember cm WHERE cm.conversationId = :conversationId AND cm.userId = :userId")
    Optional<ConversationMember> findByConversationAndUser(@Param("conversationId") String conversationId,
                                                           @Param("userId") String userId);

    /** 查询用户参与的所有会话 */
    @Query("SELECT cm FROM ConversationMember cm WHERE cm.userId = :userId AND cm.isDeleted = 0")
    List<ConversationMember> findByUserId(@Param("userId") String userId);

    /**
     * 清空会话：更新 cleared_at = now
     */
    @Modifying
    @Query("UPDATE ConversationMember cm SET cm.clearedAt = :clearedAt, cm.updatedAt = :updatedAt " +
            "WHERE cm.conversationId = :conversationId AND cm.userId = :userId")
    int clearConversation(@Param("conversationId") String conversationId,
                          @Param("userId") String userId,
                          @Param("clearedAt") LocalDateTime clearedAt,
                          @Param("updatedAt") LocalDateTime updatedAt);

    /** 查询会话内某成员的免打扰设置 */
    @Query("SELECT cm.muteNotification FROM ConversationMember cm " +
            "WHERE cm.conversationId = :conversationId AND cm.userId = :userId AND cm.isDeleted = 0")
    Integer findMuteNotification(@Param("conversationId") String conversationId,
                                 @Param("userId") String userId);
}
