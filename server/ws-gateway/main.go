package main

import (
	"bytes"
	"compress/gzip"
	"encoding/gob"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"sort"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"github.com/openimsdk/protocol/sdkws"
	"google.golang.org/protobuf/proto"
)

// Java 服务地址（消息发送 API）
const JavaServiceBaseURL = "http://openim-java-service:8082/api/message"

const (
	getNewestSeq          = 1001
	pullMsgByRange        = 1002
	sendMsg               = 1003
	sendSignalMsg         = 1004
	pullMsgBySeqList      = 1005
	getConvMaxReadSeq     = 1006
	setBackgroundStatus   = 2004
	wsSubUserOnlineStatus = 2005
)

type GeneralWsReq struct {
	ReqIdentifier int
	Token         string
	SendID        string
	OperationID   string
	MsgIncr       string
	Data          []byte
}

type GeneralWsResp struct {
	ReqIdentifier int
	ErrCode       int
	ErrMsg        string
	MsgIncr       string
	OperationID   string
	Data          []byte
}

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	CheckOrigin: func(r *http.Request) bool {
		return true
	},
}

func main() {
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte("ok"))
	})
	http.HandleFunc("/ws", handleWS)
	http.HandleFunc("/", handleWS)

	addr := ":8084"
	log.Printf("OpenIM WS gateway listening on %s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatal(err)
	}
}

func handleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("upgrade failed: %v", err)
		return
	}
	defer conn.Close()

	userID := r.URL.Query().Get("sendID")
	compression := r.URL.Query().Get("compression")
	log.Printf("ws connected userID=%s compression=%s", userID, compression)

	conn.SetReadLimit(4 << 20)
	conn.SetPongHandler(func(string) error {
		_ = conn.SetReadDeadline(time.Now().Add(90 * time.Second))
		return nil
	})
	_ = conn.SetReadDeadline(time.Now().Add(90 * time.Second))

	for {
		messageType, payload, err := conn.ReadMessage()
		if err != nil {
			log.Printf("ws read closed userID=%s err=%v", userID, err)
			return
		}
		if messageType != websocket.BinaryMessage {
			log.Printf("ignore non-binary ws message userID=%s type=%d", userID, messageType)
			continue
		}

		req, err := decodeReq(payload, compression == "gzip")
		if err != nil {
			log.Printf("decode req failed userID=%s len=%d err=%v", userID, len(payload), err)
			continue
		}

		resp := handleReq(req)
		encoded, err := encodeResp(resp, compression == "gzip")
		if err != nil {
			log.Printf("encode resp failed userID=%s reqIdentifier=%d err=%v", userID, req.ReqIdentifier, err)
			continue
		}

		if err := conn.WriteMessage(websocket.BinaryMessage, encoded); err != nil {
			log.Printf("write resp failed userID=%s reqIdentifier=%d err=%v", userID, req.ReqIdentifier, err)
			return
		}
		log.Printf("ws resp sent userID=%s reqIdentifier=%d msgIncr=%s dataLen=%d", userID, resp.ReqIdentifier, resp.MsgIncr, len(resp.Data))
	}
}

func handleReq(req *GeneralWsReq) GeneralWsResp {
	log.Printf("ws req reqIdentifier=%d sendID=%s operationID=%s msgIncr=%s dataLen=%d", req.ReqIdentifier, req.SendID, req.OperationID, req.MsgIncr, len(req.Data))

	resp := GeneralWsResp{
		ReqIdentifier: req.ReqIdentifier,
		ErrCode:       0,
		ErrMsg:        "",
		MsgIncr:       req.MsgIncr,
		OperationID:   req.OperationID,
	}

	switch req.ReqIdentifier {
	case getNewestSeq:
		data, err := proto.Marshal(&sdkws.GetMaxSeqResp{
			MaxSeqs: map[string]int64{},
			MinSeqs: map[string]int64{},
		})
		if err != nil {
			return errorResp(req, err)
		}
		resp.Data = data
	case pullMsgByRange, pullMsgBySeqList:
		data, err := proto.Marshal(&sdkws.PullMessageBySeqsResp{
			Msgs:             map[string]*sdkws.PullMsgs{},
			NotificationMsgs: map[string]*sdkws.PullMsgs{},
		})
		if err != nil {
			return errorResp(req, err)
		}
		resp.Data = data
	case sendMsg:
		// 解码 protobuf MsgData，提取消息内容并转发到 Java 服务
		msgData := &sdkws.MsgData{}
		if err := proto.Unmarshal(req.Data, msgData); err != nil {
			log.Printf("sendMsg: unmarshal MsgData failed: %v", err)
			return errorResp(req, fmt.Errorf("invalid MsgData: %w", err))
		}

		// 构建 conversationId
		conversationID := buildConversationID(msgData)
		content := string(msgData.Content)
		contentType := int(msgData.ContentType)
		if contentType == 0 {
			contentType = 1 // 默认文本消息
		}
		clientMsgID := msgData.ClientMsgID

		log.Printf("sendMsg: forwarding to Java service conversationID=%s senderID=%s contentType=%d contentLen=%d",
			conversationID, msgData.SendID, contentType, len(content))

		// 异步转发到 Java 服务（不阻塞 WebSocket 响应）
		go func() {
			serverMsgID, err := forwardToJavaService(conversationID, msgData.SendID, contentType, content)
			if err != nil {
				log.Printf("sendMsg: forward to Java service failed: %v", err)
			} else {
				log.Printf("sendMsg: forward success serverMsgID=%s clientMsgID=%s", serverMsgID, clientMsgID)
			}
		}()

		// 立即返回响应给 Flutter SDK
		respData := &sdkws.UserSendMsgResp{
			SendTime:    time.Now().UnixMilli(),
			ClientMsgID: clientMsgID,
		}
		data, err := proto.Marshal(respData)
		if err != nil {
			return errorResp(req, err)
		}
		resp.Data = data
	case sendSignalMsg, getConvMaxReadSeq, setBackgroundStatus, wsSubUserOnlineStatus:
		resp.Data = []byte{}
	default:
		resp.ErrCode = 400
		resp.ErrMsg = "unsupported reqIdentifier"
		resp.Data = []byte{}
	}
	return resp
}

func errorResp(req *GeneralWsReq, err error) GeneralWsResp {
	return GeneralWsResp{
		ReqIdentifier: req.ReqIdentifier,
		ErrCode:       500,
		ErrMsg:        err.Error(),
		MsgIncr:       req.MsgIncr,
		OperationID:   req.OperationID,
		Data:          []byte{},
	}
}

func decodeReq(payload []byte, compressed bool) (*GeneralWsReq, error) {
	var err error
	if compressed {
		payload, err = gunzip(payload)
		if err != nil {
			return nil, err
		}
	}
	var req GeneralWsReq
	if err := gob.NewDecoder(bytes.NewReader(payload)).Decode(&req); err != nil {
		return nil, err
	}
	return &req, nil
}

func encodeResp(resp GeneralWsResp, compressed bool) ([]byte, error) {
	buf := bytes.Buffer{}
	if err := gob.NewEncoder(&buf).Encode(resp); err != nil {
		return nil, err
	}
	if compressed {
		return gzipBytes(buf.Bytes())
	}
	return buf.Bytes(), nil
}

func gunzip(data []byte) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	defer reader.Close()

	buf := bytes.Buffer{}
	_, err = buf.ReadFrom(reader)
	if err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func gzipBytes(data []byte) ([]byte, error) {
	buf := bytes.Buffer{}
	writer := gzip.NewWriter(&buf)
	if _, err := writer.Write(data); err != nil {
		return nil, err
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// buildConversationID 根据 MsgData 构建会话 ID。
// 单聊: si_{sortedID1}_{sortedID2}（与 Python cs_api 保持一致）
// 群聊: 直接使用 groupID
func buildConversationID(msg *sdkws.MsgData) string {
	if msg.SessionType == 2 && msg.GroupID != "" {
		return msg.GroupID
	}
	// 单聊：两个用户 ID 排序后拼接
	ids := []string{msg.SendID, msg.RecvID}
	sort.Strings(ids)
	return fmt.Sprintf("si_%s_%s", ids[0], ids[1])
}

// SendMessageRequest 发送到 Java 服务的 JSON 请求体
type SendMessageRequest struct {
	ConversationID string `json:"conversationId"`
	SenderID       string `json:"senderId"`
	MsgType        int    `json:"msgType"`
	Content        string `json:"content"`
}

// SendMessageResponse Java 服务返回的响应
type SendMessageResponse struct {
	Code int                    `json:"code"`
	Msg  string                 `json:"msg"`
	Data *SendMessageResultData `json:"data"`
}

// SendMessageResultData 消息结果
type SendMessageResultData struct {
	MessageID string `json:"messageId"`
	Seq       int64  `json:"seq"`
}

// forwardToJavaService 将消息转发到 Java 服务进行存储和推送。
func forwardToJavaService(conversationID, senderID string, msgType int, content string) (string, error) {
	reqBody := SendMessageRequest{
		ConversationID: conversationID,
		SenderID:       senderID,
		MsgType:        msgType,
		Content:        content,
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("marshal request: %w", err)
	}

	url := strings.TrimRight(JavaServiceBaseURL, "/") + "/send"
	resp, err := http.Post(url, "application/json", bytes.NewReader(jsonData))
	if err != nil {
		return "", fmt.Errorf("http post to %s: %w", url, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("read response: %w", err)
	}

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("java service returned %d: %s", resp.StatusCode, string(body))
	}

	var result SendMessageResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return "", fmt.Errorf("unmarshal response: %w (body=%s)", err, string(body))
	}

	if result.Code != 0 {
		return "", fmt.Errorf("java service error: code=%d msg=%s", result.Code, result.Msg)
	}

	if result.Data != nil {
		log.Printf("forwardToJavaService: success messageID=%s seq=%d", result.Data.MessageID, result.Data.Seq)
		return result.Data.MessageID, nil
	}

	return "", nil
}
