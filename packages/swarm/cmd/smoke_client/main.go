package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	pb "nexus-swarm/nexus"
)

func main() {
	// 1. 連接至 Go Swarm
	conn, err := grpc.Dial(":8517", grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("did not connect to swarm: %v", err)
	}
	defer conn.Close()
	c := pb.NewNexusSwarmClient(conn)

	ctx, cancel := context.WithTimeout(context.Background(), time.Second*5)
	defer cancel()

	// 2. 觸發 PHASE_PLAN
	taskID := "T888"
	r, err := c.RunPhase(ctx, &pb.PhaseRequest{
		TaskId: taskID,
		Phase:  pb.PhaseID_PHASE_PLAN,
	})
	if err != nil {
		log.Fatalf("could not run phase: %v", err)
	}

	// 3. 輸出標準化 JSON Artifact 證據
	artifact := map[string]interface{}{
		"task_id":     taskID,
		"phase":       "PLAN",
		"status":      r.Status.String(),
		"summary":     r.Summary,
		"timestamp":   time.Now().Format(time.RFC3339),
		"residue_verify": "Checking /tmp/codex-workspaces/T888...",
	}
	
	jsonBytes, _ := json.MarshalIndent(artifact, "", "  ")
	fmt.Println(string(jsonBytes))
}
