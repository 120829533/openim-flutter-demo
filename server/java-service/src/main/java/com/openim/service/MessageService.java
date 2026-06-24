package com.openim.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.openim.dto.WsMessage;
import com.openim.model.ConversationMember;
import com.openim.model.Message;
import com.openim.repository.ConversationMemberRepository;
import com.openim.repository.MessageRepository;
import com.openim.websocket.ChatWebSocketHandler;
import com.openim.websocket.WsSessionManager;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Lazy;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.socket.WebSocketSession;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

/**
 * 消息核心服务
 * 负责：消息发送、转发、撤回、删除、清空、搜索、历史漫游、离线拉取
 * 维护 Redis：在线状态、未读计数、会话列表、消息缓存、分布式锁、seq 序列号
 */
@Service
public class MessageService {

    private static final Logger log = LoggerFactory.getLogger(MessageService.class);

    // Redis key 前缀（与 Python 服务保持一致）
    private static final String ONLINE_KEY = "online:";
    private static final String UNREAD_KEY = "unread:";
    private static final String CONV_LIST_KEY = "conv_list:";
    private static final String MSG_CACHE_KEY = "msg_cache:";
    private static final String LOCK_KEY = "lock:";
    private static final String SEQ_KEY = "seq:";

    @Autowired
    private MessageRepository messageRepository;

    @Autowired
    private ConversationMemberRepository conversationMemberRepository;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

    @Autowired
    private WsSessionManager sessionManager;

    @Autowired
    @Lazy
    private ChatWebSocketHandler chatWebSocketHandler;

    @Autowired
    private OfflinePushService offlinePushService;

    @Autowired
    private ObjectMapper objectMapper;

    @Value("${openim.redis.msg-cache-limit:200}")
    private int msgCacheLimit;

    @Value("${openim.redis.lock-ttl:10}")
    private long lockTtlSeconds;

    // ======================== 消息发送 ========================

    /**
     * 发送消息核心方法
     * 1. 生成 messageId（UUID）和 seq（Redis INCR）
     * 2. 存 MySQL
     * 3. 写 Redis 消息缓存（list，上限 200）
     * 4. 更新会话列表 sorted set
     * 5. 更新接收方未读计数（hash）
     * 6. 推送给会话内在线成员
     * 7. 离线成员调 OfflinePushService
     *
     * @param conversationId 会话 ID
     * @param senderId       发送者 ID
     * @param msgType        消息类型
     * @param content        消息内容
     * @return 已存储的消息实体
     */
    @Transactional
    public Message sendMessage(String conversationId, String senderId, Integer msgType, String content) {
        // 1. 生成 messageId 与 seq
        String messageId = UUID.randomUUID().toString().replace("-", "");
        Long seq = stringRedisTemplate.opsForValue().increment(SEQ_KEY + conversationId);

        Message message = new Message();
        message.setMessageId(messageId);
        message.setConversationId(conversationId);
        message.setSenderId(senderId);
        message.setMsgType(msgType);
        message.setContent(content);
        message.setStatus(0);
        message.setSeq(seq);
        message.setCreatedAt(LocalDateTime.now());

        // 2. 存 MySQL
        message = messageRepository.save(message);
        log.info("消息已存储: messageId={}, conversationId={}, senderId={}, seq={}",
                messageId, conversationId, senderId, seq);

        // 3. 写 Redis 消息缓存
        cacheMessage(conversationId, message);

        // 4. 更新会话列表（所有成员）
        updateConversationList(conversationId, message.getCreatedAt());

        // 5 & 6 & 7. 推送与未读计数
        dispatchMessage(message);

        return message;
    }

    /**
     * 缓存消息到 Redis list（上限 200 条）
     */
    private void cacheMessage(String conversationId, Message message) {
        try {
            String key = MSG_CACHE_KEY + conversationId;
            String json = objectMapper.writeValueAsString(message);
            stringRedisTemplate.opsForList().rightPush(key, json);
            // 裁剪到最近 200 条
            stringRedisTemplate.opsForList().trim(key, -msgCacheLimit, -1);
        } catch (Exception e) {
            log.warn("缓存消息到 Redis 失败: conversationId={}", conversationId, e);
        }
    }

    /**
     * 更新会话列表 sorted set（所有成员的会话排序）
     */
    private void updateConversationList(String conversationId, LocalDateTime lastTime) {
        double score = lastTime.toEpochSecond(java.time.ZoneOffset.UTC);
        List<ConversationMember> members = conversationMemberRepository.findActiveMembers(conversationId);
        for (ConversationMember member : members) {
            String key = CONV_LIST_KEY + member.getUserId();
            stringRedisTemplate.opsForZSet().add(key, conversationId, score);
        }
    }

    /**
     * 分发消息：推送给在线成员，离线成员推送通知
     */
    private void dispatchMessage(Message message) {
        List<ConversationMember> members = conversationMemberRepository.findActiveMembers(message.getConversationId());
        if (members.isEmpty()) {
            log.debug("会话 {} 无活跃成员，跳过分发", message.getConversationId());
            return;
        }

        WsMessage wsMsg = new WsMessage("message", message);

        for (ConversationMember member : members) {
            String userId = member.getUserId();
            // 发送者自己不推送（客户端本地已处理）
            if (userId.equals(message.getSenderId())) {
                continue;
            }

            // 更新未读计数
            incrementUnread(userId, message.getConversationId());

            // 在线推送
            if (sessionManager.isOnline(userId)) {
                Set<WebSocketSession> sessions = sessionManager.getSessions(userId);
                for (WebSocketSession session : sessions) {
                    chatWebSocketHandler.sendToSession(session, wsMsg);
                }
                log.debug("在线推送: userId={}, messageId={}", userId, message.getMessageId());
            } else {
                // 离线推送：检查免打扰设置
                Integer mute = conversationMemberRepository.findMuteNotification(
                        message.getConversationId(), userId);
                if (mute == null || mute == 0) {
                    offlinePushService.pushOfflineMessage(userId, message);
                    log.debug("离线推送: userId={}, messageId={}", userId, message.getMessageId());
                } else {
                    log.debug("用户 {} 已开启免打扰，跳过离线推送", userId);
                }
            }
        }
    }

    /**
     * 增加未读计数
     */
    private void incrementUnread(String userId, String conversationId) {
        String key = UNREAD_KEY + userId;
        stringRedisTemplate.opsForHash().increment(key, conversationId, 1);
    }

    /**
     * 清零某会话未读计数
     */
    public void clearUnread(String userId, String conversationId) {
        stringRedisTemplate.opsForHash().delete(UNREAD_KEY + userId, conversationId);
    }

    // ======================== 消息操作 ========================

    /**
     * 转发单条消息：生成新消息写入目标会话
     */
    @Transactional
    public Message forwardMessage(String messageId, String targetConversationId, String operatorId) {
        Message original = messageRepository.findByMessageId(messageId);
        if (original == null) {
            throw new IllegalArgumentException("原消息不存在: " + messageId);
        }
        // 转发生成新消息，内容相同，但 messageId/seq/时间重新生成
        return sendMessage(targetConversationId, operatorId, original.getMsgType(), original.getContent());
    }

    /**
     * 撤回消息：更新 status=1，通过 WS 通知会话成员
     */
    @Transactional
    public boolean recallMessage(String messageId) {
        int updated = messageRepository.recallMessage(messageId);
        if (updated == 0) {
            return false;
        }
        Message message = messageRepository.findByMessageId(messageId);
        if (message != null) {
            // 通过 WS 通知会话成员
            Map<String, Object> notice = new HashMap<>();
            notice.put("message_id", messageId);
            notice.put("conversation_id", message.getConversationId());
            notice.put("action", "recall");
            WsMessage wsMsg = new WsMessage("recall", notice);

            List<ConversationMember> members = conversationMemberRepository.findActiveMembers(message.getConversationId());
            for (ConversationMember member : members) {
                Set<WebSocketSession> sessions = sessionManager.getSessions(member.getUserId());
                for (WebSocketSession session : sessions) {
                    chatWebSocketHandler.sendToSession(session, wsMsg);
                }
            }
            log.info("消息已撤回: messageId={}", messageId);
        }
        return true;
    }

    /**
     * 本地单条删除：写 message_deletions 表
     */
    @Transactional
    public boolean deleteMessage(String messageId, String userId) {
        int updated = messageRepository.markMessageDeleted(messageId, userId);
        log.info("消息本地删除: messageId={}, userId={}, affected={}", messageId, userId, updated);
        return updated > 0;
    }

    /**
     * 清空会话：更新 conversation_members.cleared_at = now
     */
    @Transactional
    public boolean clearConversation(String conversationId, String userId) {
        LocalDateTime now = LocalDateTime.now();
        int updated = conversationMemberRepository.clearConversation(conversationId, userId, now, now);
        // 清零未读计数
        clearUnread(userId, conversationId);
        log.info("会话已清空: conversationId={}, userId={}", conversationId, userId);
        return updated > 0;
    }

    // ======================== 查询 ========================

    /**
     * 全局关键词检索消息
     */
    public List<Message> searchMessages(String keyword, String userId) {
        return messageRepository.searchByKeyword(keyword, userId);
    }

    /**
     * 历史消息漫游
     * 查询 seq < before_seq 且 created_at > cleared_at 的消息
     *
     * @param conversationId 会话 ID
     * @param userId         用户 ID（用于查询 cleared_at）
     * @param beforeSeq      查询此 seq 之前的消息，null 时取当前最大 seq
     * @param limit          返回条数
     */
    public List<Message> getHistoryMessages(String conversationId, String userId, Long beforeSeq, int limit) {
        // 查询用户的 cleared_at
        LocalDateTime clearedAt = conversationMemberRepository
                .findByConversationAndUser(conversationId, userId)
                .map(ConversationMember::getClearedAt)
                .orElse(null);

        // beforeSeq 为空时，使用当前最大 seq + 1
        if (beforeSeq == null || beforeSeq <= 0) {
            String maxSeqStr = stringRedisTemplate.opsForValue().get(SEQ_KEY + conversationId);
            beforeSeq = (maxSeqStr == null) ? Long.MAX_VALUE : Long.parseLong(maxSeqStr) + 1;
        }

        if (limit <= 0 || limit > 200) {
            limit = 50;
        }
        return messageRepository.findHistoryMessages(conversationId, beforeSeq, clearedAt, limit);
    }

    /**
     * 拉取离线消息
     */
    public List<Message> getOfflineMessages(String userId) {
        // 简化：拉取用户所有会话最近 100 条消息（生产可基于 last_login_at 优化）
        return messageRepository.findOfflineMessages(userId, null);
    }

    // ======================== 分布式锁 ========================

    /**
     * 尝试获取分布式锁
     *
     * @param resource 资源标识
     * @return token，获取失败返回 null
     */
    public String tryLock(String resource) {
        String token = UUID.randomUUID().toString();
        String key = LOCK_KEY + resource;
        Boolean ok = stringRedisTemplate.opsForValue()
                .setIfAbsent(key, token, lockTtlSeconds, TimeUnit.SECONDS);
        return Boolean.TRUE.equals(ok) ? token : null;
    }

    /**
     * 释放分布式锁（仅持有者可释放）
     */
    public void unlock(String resource, String token) {
        if (token == null) {
            return;
        }
        String key = LOCK_KEY + resource;
        String current = stringRedisTemplate.opsForValue().get(key);
        if (token.equals(current)) {
            stringRedisTemplate.delete(key);
        }
    }
}
