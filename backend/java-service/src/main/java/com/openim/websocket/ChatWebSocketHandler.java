package com.openim.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.openim.dto.WsMessage;
import com.openim.model.Message;
import com.openim.service.MessageService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.net.URI;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

/**
 * WebSocket 核心处理器
 * 处理 login / heartbeat / chat / pull_offline 四种消息类型
 *
 * 连接建立后客户端需先发 login（携带 token），服务端校验后注册到 WsSessionManager 并写 Redis 在线状态
 */
@Component
public class ChatWebSocketHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(ChatWebSocketHandler.class);

    private static final String ONLINE_KEY_PREFIX = "online:";
    private static final String ATTR_USER_ID = "userId";

    @Autowired
    private WsSessionManager sessionManager;

    @Autowired
    private MessageService messageService;

    @Autowired
    private StringRedisTemplate stringRedisTemplate;

    @Autowired
    private ObjectMapper objectMapper;

    @Value("${openim.redis.online-ttl:60}")
    private long onlineTtlSeconds;

    /**
     * 连接建立
     * 从 query 参数 token 中解析用户 ID（此处简化：token 即 user_id，生产应校验 JWT）
     */
    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        String userId = parseUserIdFromToken(session);
        log.info("WebSocket 连接建立: sessionId={}, userId={}", session.getId(), userId);
        // 暂存到 session 属性，等收到 login 消息后再正式注册
        if (userId != null) {
            session.getAttributes().put(ATTR_USER_ID, userId);
        }
    }

    /**
     * 收到文本消息
     */
    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        String payload = message.getPayload();
        log.debug("WebSocket 收到消息: sessionId={}, payload={}", session.getId(), payload);

        WsMessage wsMessage;
        try {
            wsMessage = objectMapper.readValue(payload, WsMessage.class);
        } catch (Exception e) {
            log.warn("WebSocket 消息解析失败: {}", payload, e);
            sendToSession(session, new WsMessage("error", "invalid message format"));
            return;
        }

        String type = wsMessage.getType();
        if (type == null) {
            sendToSession(session, new WsMessage("error", "missing type field"));
            return;
        }

        switch (type) {
            case "login":
                handleLogin(session, wsMessage);
                break;
            case "heartbeat":
                handleHeartbeat(session);
                break;
            case "chat":
                handleChat(session, wsMessage);
                break;
            case "pull_offline":
                handlePullOffline(session);
                break;
            default:
                sendToSession(session, new WsMessage("error", "unknown type: " + type));
        }
    }

    /**
     * 连接关闭
     */
    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        String userId = sessionManager.getUserId(session);
        sessionManager.remove(session);
        log.info("WebSocket 连接关闭: sessionId={}, userId={}, status={}",
                session.getId(), userId, status);

        // 若该用户已无任何连接，删除 Redis 在线状态
        if (userId != null && !sessionManager.isOnline(userId)) {
            stringRedisTemplate.delete(ONLINE_KEY_PREFIX + userId);
            log.info("用户 {} 已下线，清除在线状态", userId);
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.error("WebSocket 传输错误: sessionId={}", session.getId(), exception);
        try {
            if (session.isOpen()) {
                session.close(CloseStatus.SERVER_ERROR);
            }
        } catch (IOException e) {
            log.warn("关闭 WebSocket 会话失败", e);
        }
    }

    // ======================== 消息处理 ========================

    /**
     * 处理 login：校验 token，注册会话，写 Redis 在线状态
     */
    private void handleLogin(WebSocketSession session, WsMessage wsMessage) throws IOException {
        // 优先从 query 参数获取，其次从 data 获取
        String userId = (String) session.getAttributes().get(ATTR_USER_ID);
        if (userId == null && wsMessage.getData() instanceof Map) {
            Object tokenObj = ((Map<?, ?>) wsMessage.getData()).get("token");
            if (tokenObj != null) {
                userId = parseUserIdFromTokenStr(tokenObj.toString());
            }
        }
        if (userId == null || userId.isEmpty()) {
            sendToSession(session, new WsMessage("error", "login failed: missing token"));
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }

        // 注册到会话管理器
        sessionManager.register(userId, session);
        session.getAttributes().put(ATTR_USER_ID, userId);

        // 写 Redis 在线状态
        String onlineKey = ONLINE_KEY_PREFIX + userId;
        stringRedisTemplate.opsForValue().set(onlineKey, "1", onlineTtlSeconds, TimeUnit.SECONDS);

        Map<String, Object> resp = new HashMap<>();
        resp.put("result", "ok");
        resp.put("userId", userId);
        sendToSession(session, new WsMessage("login_ack", resp));
        log.info("用户 {} 登录成功", userId);
    }

    /**
     * 处理 heartbeat：刷新 Redis 在线状态 TTL，回复 pong
     */
    private void handleHeartbeat(WebSocketSession session) throws IOException {
        String userId = sessionManager.getUserId(session);
        if (userId == null) {
            sendToSession(session, new WsMessage("error", "not logged in"));
            return;
        }
        // 刷新在线状态 TTL
        stringRedisTemplate.opsForValue().set(
                ONLINE_KEY_PREFIX + userId, "1", onlineTtlSeconds, TimeUnit.SECONDS);
        sendToSession(session, new WsMessage("pong", System.currentTimeMillis()));
    }

    /**
     * 处理 chat：发送消息
     * data={conversation_id, msg_type, content}
     */
    private void handleChat(WebSocketSession session, WsMessage wsMessage) {
        String senderId = sessionManager.getUserId(session);
        if (senderId == null) {
            sendToSession(session, new WsMessage("error", "not logged in"));
            return;
        }

        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> data = (Map<String, Object>) wsMessage.getData();
            if (data == null) {
                sendToSession(session, new WsMessage("error", "empty data"));
                return;
            }
            String conversationId = (String) data.get("conversation_id");
            Integer msgType = data.get("msg_type") instanceof Number
                    ? ((Number) data.get("msg_type")).intValue() : 1;
            String content = data.get("content") == null ? "" : data.get("content").toString();

            if (conversationId == null || conversationId.isEmpty()) {
                sendToSession(session, new WsMessage("error", "missing conversation_id"));
                return;
            }

            // 调用消息服务发送
            Message msg = messageService.sendMessage(conversationId, senderId, msgType, content);

            Map<String, Object> resp = new HashMap<>();
            resp.put("result", "ok");
            resp.put("message_id", msg.getMessageId());
            resp.put("seq", msg.getSeq());
            sendToSession(session, new WsMessage("chat_ack", resp));
        } catch (Exception e) {
            log.error("处理 chat 消息失败", e);
            Map<String, Object> err = new HashMap<>();
            err.put("result", "fail");
            err.put("reason", e.getMessage());
            sendToSession(session, new WsMessage("chat_ack", err));
        }
    }

    /**
     * 处理 pull_offline：拉取离线消息
     */
    private void handlePullOffline(WebSocketSession session) {
        String userId = sessionManager.getUserId(session);
        if (userId == null) {
            sendToSession(session, new WsMessage("error", "not logged in"));
            return;
        }
        try {
            List<Message> offlineMessages = messageService.getOfflineMessages(userId);
            Map<String, Object> resp = new HashMap<>();
            resp.put("messages", offlineMessages);
            resp.put("count", offlineMessages.size());
            sendToSession(session, new WsMessage("pull_offline_ack", resp));
        } catch (Exception e) {
            log.error("拉取离线消息失败", e);
            Map<String, Object> err = new HashMap<>();
            err.put("result", "fail");
            err.put("reason", e.getMessage());
            sendToSession(session, new WsMessage("pull_offline_ack", err));
        }
    }

    // ======================== 工具方法 ========================

    /**
     * 从连接 URL 的 query 参数 token 中解析用户 ID
     * 简化实现：token 直接作为 user_id（生产环境应解析 JWT）
     */
    private String parseUserIdFromToken(WebSocketSession session) {
        URI uri = session.getUri();
        if (uri == null || uri.getQuery() == null) {
            return null;
        }
        String query = uri.getQuery();
        for (String param : query.split("&")) {
            String[] kv = param.split("=", 2);
            if (kv.length == 2 && "token".equals(kv[0])) {
                return parseUserIdFromTokenStr(kv[1]);
            }
        }
        return null;
    }

    /**
     * 从 token 字符串解析用户 ID
     * 简化实现：token 即为 userId
     */
    private String parseUserIdFromTokenStr(String token) {
        // 生产环境应在此校验 JWT 并提取 userId
        return token;
    }

    /**
     * 向单个 session 发送消息
     */
    public void sendToSession(WebSocketSession session, WsMessage message) {
        if (session == null || !session.isOpen()) {
            return;
        }
        try {
            String json = objectMapper.writeValueAsString(message);
            session.sendMessage(new TextMessage(json));
        } catch (IOException e) {
            log.warn("发送 WebSocket 消息失败: sessionId={}", session.getId(), e);
        }
    }
}
