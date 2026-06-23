package com.openim.dto;

import lombok.Data;

/**
 * 发送消息请求 DTO（REST 接口用）
 */
@Data
public class SendMessageRequest {

    /** 会话 ID */
    private String conversationId;

    /** 消息类型：1=文本 2=图片 3=语音 4=视频 5=文件 */
    private Integer msgType;

    /** 消息内容 */
    private String content;

    /** 发送者用户 ID（REST 调用时传入，WS 调用时从登录态获取） */
    private String senderId;
}
