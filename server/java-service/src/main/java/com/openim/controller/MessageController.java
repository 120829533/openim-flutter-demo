package com.openim.controller;

import com.openim.dto.SendMessageRequest;
import com.openim.model.Message;
import com.openim.service.MessageService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 消息 REST 接口
 * 统一响应格式: {code, msg, data}
 * 路径前缀: /api/message
 */
@RestController
@RequestMapping("/api/message")
public class MessageController {

    private static final Logger log = LoggerFactory.getLogger(MessageController.class);

    @Autowired
    private MessageService messageService;

    /**
     * 发送消息
     * POST /api/message/send
     */
    @PostMapping("/send")
    public ResponseEntity<Map<String, Object>> send(@RequestBody SendMessageRequest request) {
        Map<String, Object> result = new HashMap<>();
        try {
            if (request.getConversationId() == null || request.getSenderId() == null) {
                return fail("conversation_id 和 sender_id 不能为空");
            }
            Integer msgType = request.getMsgType() == null ? 1 : request.getMsgType();
            Message message = messageService.sendMessage(
                    request.getConversationId(),
                    request.getSenderId(),
                    msgType,
                    request.getContent());
            result.put("code", 0);
            result.put("msg", "ok");
            result.put("data", message);
            return ResponseEntity.ok(result);
        } catch (Exception e) {
            log.error("发送消息失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 转发单条消息
     * POST /api/message/forward
     * body: {message_id, target_conversation_id}
     */
    @PostMapping("/forward")
    public ResponseEntity<Map<String, Object>> forward(@RequestBody Map<String, String> body) {
        try {
            String messageId = body.get("message_id");
            String targetConversationId = body.get("target_conversation_id");
            String operatorId = body.getOrDefault("user_id", "system");
            if (messageId == null || targetConversationId == null) {
                return fail("message_id 和 target_conversation_id 不能为空");
            }
            Message message = messageService.forwardMessage(messageId, targetConversationId, operatorId);
            return ok(message);
        } catch (Exception e) {
            log.error("转发消息失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 撤回消息
     * POST /api/message/recall
     * body: {message_id}
     */
    @PostMapping("/recall")
    public ResponseEntity<Map<String, Object>> recall(@RequestBody Map<String, String> body) {
        try {
            String messageId = body.get("message_id");
            if (messageId == null) {
                return fail("message_id 不能为空");
            }
            boolean success = messageService.recallMessage(messageId);
            if (success) {
                return ok("已撤回");
            } else {
                return fail("消息不存在或已撤回");
            }
        } catch (Exception e) {
            log.error("撤回消息失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 本地单条删除
     * POST /api/message/delete
     * body: {message_id, user_id}
     */
    @PostMapping("/delete")
    public ResponseEntity<Map<String, Object>> delete(@RequestBody Map<String, String> body) {
        try {
            String messageId = body.get("message_id");
            String userId = body.get("user_id");
            if (messageId == null || userId == null) {
                return fail("message_id 和 user_id 不能为空");
            }
            boolean success = messageService.deleteMessage(messageId, userId);
            if (success) {
                return ok("已删除");
            } else {
                return fail("删除失败");
            }
        } catch (Exception e) {
            log.error("删除消息失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 清空会话
     * POST /api/message/clear
     * body: {conversation_id, user_id}
     */
    @PostMapping("/clear")
    public ResponseEntity<Map<String, Object>> clear(@RequestBody Map<String, String> body) {
        try {
            String conversationId = body.get("conversation_id");
            String userId = body.get("user_id");
            if (conversationId == null || userId == null) {
                return fail("conversation_id 和 user_id 不能为空");
            }
            boolean success = messageService.clearConversation(conversationId, userId);
            if (success) {
                return ok("已清空");
            } else {
                return fail("清空失败");
            }
        } catch (Exception e) {
            log.error("清空会话失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 全局关键词检索
     * GET /api/message/search?keyword=&user_id=
     */
    @GetMapping("/search")
    public ResponseEntity<Map<String, Object>> search(@RequestParam("keyword") String keyword,
                                                       @RequestParam("user_id") String userId) {
        try {
            if (keyword == null || keyword.trim().isEmpty()) {
                return fail("keyword 不能为空");
            }
            List<Message> messages = messageService.searchMessages(keyword, userId);
            return ok(messages);
        } catch (Exception e) {
            log.error("搜索消息失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 历史消息漫游
     * GET /api/message/history?conversation_id=&user_id=&before_seq=&limit=
     */
    @GetMapping("/history")
    public ResponseEntity<Map<String, Object>> history(@RequestParam("conversation_id") String conversationId,
                                                        @RequestParam("user_id") String userId,
                                                        @RequestParam(value = "before_seq", required = false) Long beforeSeq,
                                                        @RequestParam(value = "limit", defaultValue = "50") int limit) {
        try {
            if (conversationId == null || userId == null) {
                return fail("conversation_id 和 user_id 不能为空");
            }
            List<Message> messages = messageService.getHistoryMessages(conversationId, userId, beforeSeq, limit);
            return ok(messages);
        } catch (Exception e) {
            log.error("查询历史消息失败", e);
            return fail(e.getMessage());
        }
    }

    /**
     * 拉取离线消息
     * GET /api/message/offline?user_id=
     */
    @GetMapping("/offline")
    public ResponseEntity<Map<String, Object>> offline(@RequestParam("user_id") String userId) {
        try {
            if (userId == null) {
                return fail("user_id 不能为空");
            }
            List<Message> messages = messageService.getOfflineMessages(userId);
            return ok(messages);
        } catch (Exception e) {
            log.error("拉取离线消息失败", e);
            return fail(e.getMessage());
        }
    }

    // ======================== 统一响应工具 ========================

    private ResponseEntity<Map<String, Object>> ok(Object data) {
        Map<String, Object> result = new HashMap<>();
        result.put("code", 0);
        result.put("msg", "ok");
        result.put("data", data);
        return ResponseEntity.ok(result);
    }

    private ResponseEntity<Map<String, Object>> fail(String msg) {
        Map<String, Object> result = new HashMap<>();
        result.put("code", 1);
        result.put("msg", msg);
        result.put("data", null);
        return ResponseEntity.ok(result);
    }
}
