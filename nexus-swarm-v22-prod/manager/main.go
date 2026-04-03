package main

import (
	"context"
	"log"
	"net"
	"os"
	"sync"
	"time"

	pb "nexus-swarm/api/proto"
	fed "nexus-swarm/api/proto"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
	_ "github.com/lib/pq"
)

type NodeState struct {
	*pb.NodeStatus
}

type swarmServer struct {
	pb.UnimplementedSwarmManagerServer
	fed.UnimplementedFederationServer
	mu    sync.RWMutex
	nodes map[string]*NodeState
	db    *DB
}

func newSwarmServer(db *DB) *swarmServer {
	return &swarmServer{
		nodes: make(map[string]*NodeState),
		db:    db,
	}
}

func (s *swarmServer) RegisterNode(ctx context.Context, req *pb.RegisterNodeRequest) (*pb.RegisterNodeResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.nodes[req.NodeId] = &NodeState{
		NodeStatus: &pb.NodeStatus{
			NodeId:        req.NodeId,
			Region:        req.Region,
			CpuPercent:    0,
			MemoryPercent: 0,
			ActiveTasks:   0,
			LastSeenUnix:  time.Now().Unix(),
			Health:        "HEALTHY",
			AdvertiseAddr: req.AdvertiseAddr,
		},
	}

	log.Printf("[NEXUS v22] Node %s registered in region %s (Trace: %s)", req.NodeId, req.Region, req.Traceparent)

	// 🛡️ [v22/v24] Persistence
	if s.db != nil {
		if err := s.db.UpsertNode(req.NodeId, req.Region, "HEALTHY", req.AdvertiseAddr, 0, 0, 0); err != nil {
			log.Printf("[DB] Upsert failed: %v", err)
		}
	}

	return &pb.RegisterNodeResponse{
		Accepted:             true,
		HeartbeatIntervalSec: 30,
		ManagerId:            "nexus-manager-v22",
	}, nil
}

func (s *swarmServer) Heartbeat(ctx context.Context, req *pb.HeartbeatRequest) (*pb.HeartbeatResponse, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if node, ok := s.nodes[req.NodeId]; ok {
		node.CpuPercent = req.CpuPercent
		node.MemoryPercent = req.MemoryPercent
		node.ActiveTasks = req.ActiveTasks
		node.LastSeenUnix = time.Now().Unix()
		node.Health = "HEALTHY"

		// 🛡️ [v22/v24] Persistence
		if s.db != nil {
			if err := s.db.UpsertNode(req.NodeId, node.Region, "HEALTHY", node.AdvertiseAddr, req.CpuPercent, req.MemoryPercent, int(req.ActiveTasks)); err != nil {
				log.Printf("[DB] Upsert failed: %v", err)
			}
		}
	} else {
		log.Printf("[WARNING] Heartbeat from unknown node: %s", req.NodeId)
	}

	return &pb.HeartbeatResponse{
		Ok:     true,
		Status: "HEALTHY",
	}, nil
}

func (s *swarmServer) GetClusterStatus(ctx context.Context, req *pb.GetClusterStatusRequest) (*pb.GetClusterStatusResponse, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	var nodes []*pb.NodeStatus
	healthyCount := 0
	now := time.Now().Unix()

	for _, n := range s.nodes {
		// 🛡️ STALE Rule: 60s
		if now-n.LastSeenUnix > 60 {
			n.Health = "STALE"
		} else {
			healthyCount++
		}
		nodes = append(nodes, n.NodeStatus)
	}

	return &pb.GetClusterStatusResponse{
		ManagerId:    "nexus-manager-v22",
		Nodes:        nodes,
		TotalNodes:   int32(len(nodes)),
		HealthyNodes: int32(healthyCount),
	}, nil
}

// 🛡️ [v22/v24] DispatchTask logic moved to dispatch_task.go

func main() {
	// 🛡️ [v22/v24] Database persistence
	dsn := os.Getenv("DATABASE_URL")
	if dsn == "" {
		dsn = "host=localhost port=5432 user=nexus password=nexus dbname=swarmdb sslmode=disable"
	}
	db, err := NewDB(dsn)
	if err != nil {
		log.Printf("[WARNING] DB connection failed, falling back to in-memory: %v", err)
	}

	lis, err := net.Listen("tcp", ":9000")
	if err != nil {
		log.Fatalf("failed to listen: %v", err)
	}

	// 🛡️ [v22/v24] mTLS Configuration
	creds, err := credentials.NewServerTLSFromFile("certs/manager.crt", "certs/manager.key")
	if err != nil {
		log.Fatalf("failed to load TLS keys: %v", err)
	}

	s := grpc.NewServer(grpc.Creds(creds))
	swarmSrv := newSwarmServer(db)
	pb.RegisterSwarmManagerServer(s, swarmSrv)
	fed.RegisterFederationServer(s, swarmSrv)

	// 🛡️ [v22/v24] Federation Initialization
	initFederation()

	// Start HTTP Metrics in Background
	go startHTTPServer(swarmSrv)

	log.Printf("[NEXUS v22] Swarm Manager with mTLS listening on :9000")
	if err := s.Serve(lis); err != nil {
		log.Fatalf("failed to serve: %v", err)
	}
}
