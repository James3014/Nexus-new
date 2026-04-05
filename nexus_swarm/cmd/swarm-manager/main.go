package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"

	pb "nexus-swarm/api/proto"
	"nexus-swarm/pkg/index"

	"github.com/prometheus/client_golang/prometheus/promhttp"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

type server struct {
	pb.UnimplementedSwarmManagerServer
	processor *index.StreamProcessor
}

func (s *server) Heartbeat(ctx context.Context, req *pb.HeartbeatReq) (*pb.HeartbeatResp, error) {
	log.Printf("💓 [Heartbeat] From Node: %s", req.NodeId)
	return &pb.HeartbeatResp{Accepted: true, SyncTimestamp: req.Timestamp}, nil
}

func (s *server) SensingStream(stream pb.SwarmManager_SensingStreamServer) error {
	return s.processor.HandleSensingStream(stream)
}

func (s *server) Sensing(ctx context.Context, req *pb.SensingReq) (*pb.SensingResp, error) {
	return &pb.SensingResp{NodeId: "MANAGER_PRIMARY", Status: "STANDBY"}, nil
}

func startMetricsServer(port int) {
	http.Handle("/metrics", promhttp.Handler())
	log.Printf("📊 [Metrics] Starting Prometheus exporter on port %d", port)
	if err := http.ListenAndServe(fmt.Sprintf(":%d", port), nil); err != nil {
		log.Fatalf("❌ Metrics server failed: %v", err)
	}
}

func startHealthServer(port int) {
	http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, "OK")
	})
	log.Printf("🩺 [Health] Starting health check on port %d", port)
	if err := http.ListenAndServe(fmt.Sprintf(":%d", port), nil); err != nil {
		log.Fatalf("❌ Health server failed: %v", err)
	}
}

func main() {
	grpcPort := flag.Int("port", 8516, "GRPC port")
	metricsPort := flag.Int("metrics-port", 8518, "Metrics port")
	flag.Parse()

	// 📊 啟動 Prometheus 與 Health 服務
	go startMetricsServer(*metricsPort)
	go startHealthServer(*grpcPort + 1000) // 假設 Health 在 9516 或依 User 指定港口

	log.Printf("🚀 [Nexus Swarm] Manager v0.2 starting on port %d", *grpcPort)

	lis, err := net.Listen("tcp", fmt.Sprintf(":%d", *grpcPort))
	if err != nil {
		log.Fatalf("❌ failed to listen: %v", err)
	}

	s := grpc.NewServer()
	pb.RegisterSwarmManagerServer(s, &server{
		processor: &index.StreamProcessor{},
	})
	reflection.Register(s)

	if err := s.Serve(lis); err != nil {
		log.Fatalf("❌ failed to serve: %v", err)
	}
}
