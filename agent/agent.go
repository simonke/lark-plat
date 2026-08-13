package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os/exec"
	"runtime"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const (
	msgTypeHeartbeat = "heartbeat"
	msgTypePing      = "ping"
	msgTypePong      = "pong"
	msgTypeDispatch  = "dispatch"
	msgTypeResult    = "result"
)

// Message is the envelope exchanged with the lark-plat server (api-design §12).
type Message struct {
	Type    string          `json:"type"`
	TaskID  string          `json:"task_id,omitempty"`
	Seq     int64           `json:"seq,omitempty"`
	Payload json.RawMessage `json:"payload,omitempty"`
	At      int64           `json:"at"`
}

// Agent maintains the WebSocket connection and runs dispatched commands.
type Agent struct {
	ServerURL string
	Headers   http.Header
	Interval  time.Duration

	conn     *websocket.Conn
	connMu   sync.Mutex
	running  sync.Map // running command per seq
}

func (a *Agent) Run(ctx context.Context) error {
	for {
		if err := a.connect(ctx); err != nil {
			log.Printf("connect failed: %v; retrying in 3s", err)
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(3 * time.Second):
				continue
			}
		}
		errc := a.heartbeatLoop(ctx)
		if err := <-errc; err != nil {
			log.Printf("connection error: %v; reconnecting", err)
		}
		a.closeConn()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Second):
		}
	}
}

func (a *Agent) connect(ctx context.Context) error {
	a.connMu.Lock()
	defer a.connMu.Unlock()
	conn, resp, err := websocket.DefaultDialer.DialContext(ctx, a.ServerURL, a.Headers)
	if err != nil {
		if resp != nil {
			return fmt.Errorf("dial %s: %s (status %d)", a.ServerURL, err, resp.StatusCode)
		}
		return fmt.Errorf("dial %s: %w", a.ServerURL, err)
	}
	a.conn = conn
	log.Printf("connected to %s", a.ServerURL)
	return nil
}

func (a *Agent) closeConn() {
	a.connMu.Lock()
	defer a.connMu.Unlock()
	if a.conn != nil {
		_ = a.conn.Close()
		a.conn = nil
	}
}

// heartbeatLoop pings and reads incoming messages until the connection drops.
func (a *Agent) heartbeatLoop(ctx context.Context) <-chan error {
	errc := make(chan error, 1)
	go func() {
		ticker := time.NewTicker(a.Interval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				errc <- ctx.Err()
				return
			case <-ticker.C:
				a.connMu.Lock()
				conn := a.conn
				a.connMu.Unlock()
				if conn == nil {
					errc <- fmt.Errorf("no connection")
					return
				}
				hb := Message{Type: msgTypeHeartbeat, At: time.Now().UnixMilli()}
				if err := conn.WriteJSON(hb); err != nil {
					errc <- err
					return
				}
			default:
				conn := a.conn
				if conn == nil {
					errc <- fmt.Errorf("no connection")
					return
				}
				if err := conn.SetReadDeadline(time.Now().Add(3 * a.Interval)); err != nil {
					errc <- err
					return
				}
				var msg Message
				if err := conn.ReadJSON(&msg); err != nil {
					errc <- err
					return
				}
				a.handle(ctx, msg)
			}
		}
	}()
	return errc
}

func (a *Agent) handle(ctx context.Context, msg Message) {
	switch msg.Type {
	case msgTypePing:
		_ = a.write(Message{Type: msgTypePong, Seq: msg.Seq, At: time.Now().UnixMilli()})
	case msgTypeDispatch:
		go a.runCommand(ctx, msg)
	case msgTypeHeartbeat:
		// server-initiated heartbeat probe; reply pong
		_ = a.write(Message{Type: msgTypePong, Seq: msg.Seq, At: time.Now().UnixMilli()})
	}
}

func (a *Agent) write(msg Message) error {
	a.connMu.Lock()
	defer a.connMu.Unlock()
	if a.conn == nil {
		return fmt.Errorf("no connection")
	}
	return a.conn.WriteJSON(msg)
}

func (a *Agent) runCommand(ctx context.Context, msg Message) {
	var payload struct {
		Command string   `json:"command"`
		Script  string   `json:"script,omitempty"`
		Timeout int      `json:"timeout_sec"`
		Args    []string `json:"args,omitempty"`
	}
	if err := json.Unmarshal(msg.Payload, &payload); err != nil {
		_ = a.sendResult(msg.Seq, false, "", "invalid payload")
		return
	}

	timeout := time.Duration(payload.Timeout) * time.Second
	if timeout <= 0 {
		timeout = 300 * time.Second
	}
	cmdCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	var cmd *exec.Cmd
	if payload.Script != "" {
		cmd = runScript(cmdCtx, payload.Script)
	} else {
		cmd = runCommand(cmdCtx, payload.Command)
	}
	output, err := cmd.CombinedOutput()
	if err != nil {
		_ = a.sendResult(msg.Seq, false, string(output), err.Error())
		return
	}
	_ = a.sendResult(msg.Seq, true, string(output), "")
}

func runCommand(ctx context.Context, line string) *exec.Cmd {
	if runtime.GOOS == "windows" {
		return exec.CommandContext(ctx, "cmd", "/c", line)
	}
	return exec.CommandContext(ctx, "sh", "-c", line)
}

func runScript(ctx context.Context, script string) *exec.Cmd {
	if runtime.GOOS == "windows" {
		return exec.CommandContext(ctx, "cmd", "/c", script)
	}
	return exec.CommandContext(ctx, "sh", "-c", script)
}

func (a *Agent) sendResult(seq int64, ok bool, output, errMsg string) error {
	resp := struct {
		OK      bool   `json:"ok"`
		Output  string `json:"output"`
		Error   string `json:"error,omitempty"`
	}{
		OK:     ok,
		Output: output,
		Error:  errMsg,
	}
	data, _ := json.Marshal(resp)
	return a.write(Message{Type: msgTypeResult, Seq: seq, Payload: data, At: time.Now().UnixMilli()})
}
