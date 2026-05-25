package main

import (
	"context"
	"net"
	"net/http"
	"testing"
	"time"
	"google.golang.org/grpc"
	pb "nexus-swarm/nexus"
)

type mockCoreClient struct {
	pb.NexusCoreClient
}

func (m *mockCoreClient) LeaseWorktree(ctx context.Context, in *pb.LeaseRequest, opts ...grpc.CallOption) (*pb.WorktreeLease, error) {
	return &pb.WorktreeLease{
		LeaseId: "L-test",
		Path:    "/tmp/test-worktree",
	}, nil
}

func (m *mockCoreClient) CancelLease(ctx context.Context, in *pb.CancelLeaseRequest, opts ...grpc.CallOption) (*pb.ActionResponse, error) {
	return &pb.ActionResponse{
		Success:      true,
		ResidueCount: 0,
	}, nil
}

func TestRunPhaseAsync(t *testing.T) {
	// Spin up a dummy slow HTTP server on port 8080
	l, err := net.Listen("tcp", "127.0.0.1:8080")
	if err == nil {
		srv := &http.Server{
			Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				time.Sleep(300 * time.Millisecond) // Slow response
				w.Write([]byte(`{"content": "Audit passed"}`))
			}),
		}
		go srv.Serve(l)
		defer srv.Close()
	}

	s := &swarmServer{
		coreClient: &mockCoreClient{},
	}
	
	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), time.Second*5)
	defer cancel()
	
	outcome, err := s.RunPhase(ctx, &pb.PhaseRequest{
		TaskId: "T-test",
		Phase:  pb.PhaseID_PHASE_PLAN,
	})
	
	duration := time.Since(start)
	if err != nil {
		t.Fatalf("RunPhase failed: %v", err)
	}
	
	if outcome.Status != pb.PhaseOutcome_SUCCESS {
		t.Errorf("Expected SUCCESS status, got %v", outcome.Status)
	}
	
	// Because callBrainAudit is currently synchronous, it will block for 300ms, failing this check.
	if duration > 100*time.Millisecond {
		t.Errorf("RunPhase took too long: %v (expected < 100ms)", duration)
	}
}
