package com.openim.service;

import com.openim.model.Message;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 离线推送服务
 * 适配个推（Getui）/ Firebase 等推送渠道
 * 当前为桩实现，仅打印日志，预留接口供后续接入真实推送 SDK
 */
@Service
public class OfflinePushService {

    private static final Logger log = LoggerFactory.getLogger(OfflinePushService.class);

    @Value("${openim.file-service.url:http://openim-file-service:8083}")
    private String fileServiceUrl;

    /**
     * 推送渠道枚举
     */
    public enum PushChannel {
        /** 个推 */
        GETUI,
        /** Firebase 云消息 */
        FIREBASE,
        /** APNs（iOS） */
        APNS
    }

    /**
     * 向离线用户推送消息通知
     *
     * @param userId   接收用户 ID
     * @param message  消息内容
     * @param channel  推送渠道
     */
    public void pushOfflineMessage(String userId, Message message, PushChannel channel) {
        if (userId == null || message == null) {
            return;
        }
        log.info("[离线推送] channel={}, userId={}, messageId={}, conversationId={}, msgType={}, content={}",
                channel, userId, message.getMessageId(), message.getConversationId(),
                message.getMsgType(), truncate(message.getContent(), 50));

        // 根据渠道分发（桩实现）
        switch (channel) {
            case GETUI:
                pushViaGetui(userId, message);
                break;
            case FIREBASE:
                pushViaFirebase(userId, message);
                break;
            case APNS:
                pushViaApns(userId, message);
                break;
            default:
                log.warn("未知推送渠道: {}", channel);
        }
    }

    /**
     * 默认推送（自动选择渠道）
     */
    public void pushOfflineMessage(String userId, Message message) {
        // 默认使用个推（国内场景）
        pushOfflineMessage(userId, message, PushChannel.GETUI);
    }

    /**
     * 个推推送（桩实现）
     * 生产环境应集成个推 SDK：com.gexin.platform/gexin-rp-sdk-http
     */
    private void pushViaGetui(String userId, Message message) {
        // TODO: 接入个推 SDK
        // 1. 根据 userId 查询 cid（个推客户端标识）
        // 2. 构建推送消息体（标题、内容、透传）
        // 3. 调用 IGtPush.pushMessageToSingle()
        log.info("[个推桩] 模拟向用户 {} 推送消息 {}", userId, message.getMessageId());
    }

    /**
     * Firebase 云消息推送（桩实现）
     * 生产环境应集成 firebase-admin SDK
     */
    private void pushViaFirebase(String userId, Message message) {
        // TODO: 接入 Firebase Admin SDK
        // 1. 根据 userId 查询 FCM token
        // 2. 构建 Message 对象
        // 3. 调用 FirebaseMessaging.getInstance().send()
        log.info("[Firebase桩] 模拟向用户 {} 推送消息 {}", userId, message.getMessageId());
    }

    /**
     * APNs 推送（桩实现）
     */
    private void pushViaApns(String userId, Message message) {
        // TODO: 接入 APNs
        log.info("[APNs桩] 模拟向用户 {} 推送消息 {}", userId, message.getMessageId());
    }

    /**
     * 截断字符串用于日志
     */
    private String truncate(String s, int maxLen) {
        if (s == null) {
            return "";
        }
        return s.length() <= maxLen ? s : s.substring(0, maxLen) + "...";
    }
}
