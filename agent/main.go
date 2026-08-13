package main

import (
	"context"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	serverURL := flag.String("server", "ws://127.0.0.1:8000/api/v1/agent/ws", "lark-plat server WS URL")
	agentToken := flag.String("token", "", "agent registration token")
	agentID := flag.String("id", "", "agent id")
	interval := flag.Duration("interval", 30*time.Second, "heartbeat interval")
	flag.Parse()

	if *agentToken == "" {
		log.Fatal("--token is required (agent registration token)")
	}
	if *agentID == "" {
		log.Fatal("--id is required (agent id)")
	}

	headers := http.Header{}
	headers.Set("X-Agent-Token", *agentToken)
	headers.Set("X-Agent-Id", *agentID)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	agent := &Agent{
		ServerURL: *serverURL,
		Headers:   headers,
		Interval:  *interval,
	}
	if err := agent.Run(ctx); err != nil {
		log.Fatalf("agent exited: %v", err)
	}
	log.Println("agent stopped")
}
