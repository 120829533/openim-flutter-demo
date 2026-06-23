package com.openim.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.WebSocketSession;

import java.util.Collections;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * WebSocket 会话管理器
 * 维护 user_id -> Set<WebSocketSession> 映射，支持同一用户多设备登录
 */
@Component
public class WsSessionManager {

    private static final Logger log = LoggerFactory.getLogger(WsSessionManager.class);

    /**
     * 用户 ID -> 该用户所有设备的 WebSocket 连接集合
     * 使用 ConcurrentHashMap + synchronized Set 保证线程安全
     */
    private final Map<String, Set<WebSocketSession>> userSessions = new ConcurrentHashMap<>();

    /**
     * WebSocketSession -> 用户 ID 的反向映射，便于连接关闭时查找
     */
    private final Map<String, String> sessionUserMap = new ConcurrentHashMap<>();

    /**
     * 注册用户连接
     *
     * @param userId  用户 ID
     * @param session WebSocket 连接
     */
    public void register(String userId, WebSocketSession session) {
        if (userId == null || session == null) {
            return;
        }
        userSessions.computeIfAbsent(userId, k -> Collections.synchronizedSet(new HashSet<>())).add(session);
        sessionUserMap.put(session.getId(), userId);
        log.info("WebSocket 注册: userId={}, sessionId={}, 当前连接数={}",
                userId, session.getId(), getOnlineCount());
    }

    /**
     * 移除用户连接
     *
     * @param session 待移除的连接
     */
    public void remove(WebSocketSession session) {
        if (session == null) {
            return;
        }
        String userId = sessionUserMap.remove(session.getId());
        if (userId != null) {
            Set<WebSocketSession> sessions = userSessions.get(userId);
            if (sessions != null) {
                sessions.remove(session);
                // 若该用户已无任何连接，移除整个 entry
                if (sessions.isEmpty()) {
                    userSessions.remove(userId);
                }
            }
            log.info("WebSocket 移除: userId={}, sessionId={}, 当前连接数={}",
                    userId, session.getId(), getOnlineCount());
        }
    }

    /**
     * 获取用户所有连接（多设备）
     *
     * @param userId 用户 ID
     * @return 连接集合，可能为空
     */
    public Set<WebSocketSession> getSessions(String userId) {
        Set<WebSocketSession> sessions = userSessions.get(userId);
        if (sessions == null) {
            return Collections.emptySet();
        }
        return sessions;
    }

    /**
     * 判断用户是否在线（至少有一个活跃连接）
     *
     * @param userId 用户 ID
     * @return true=在线
     */
    public boolean isOnline(String userId) {
        Set<WebSocketSession> sessions = userSessions.get(userId);
        return sessions != null && !sessions.isEmpty();
    }

    /**
     * 获取当前在线用户总数
     *
     * @return 在线用户数
     */
    public int getOnlineUserCount() {
        return userSessions.size();
    }

    /**
     * 获取当前总连接数（含多设备）
     *
     * @return 连接总数
     */
    public int getOnlineCount() {
        return userSessions.values().stream().mapToInt(Set::size).sum();
    }

    /**
     * 根据连接获取用户 ID
     *
     * @param session 连接
     * @return 用户 ID，未注册返回 null
     */
    public String getUserId(WebSocketSession session) {
        if (session == null) {
            return null;
        }
        return sessionUserMap.get(session.getId());
    }
}
