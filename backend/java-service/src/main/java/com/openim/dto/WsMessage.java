package com.openim.dto;

import lombok.Data;

/**
 * WebSocket 收发消息体
 * 格式: {type, data}
 * type 取值: login / heartbeat / chat / pull_offline / pong / message / recall / notice
 */
@Data
public class WsMessage {

    /** 消息类型 */
    private String type;

    /** 消息数据（具体结构由 type 决定，用 Object 便于序列化） */
    private Object data;

    public WsMessage() {
    }

    public WsMessage(String type, Object data) {
        this.type = type;
        this.data = data;
    }
}
