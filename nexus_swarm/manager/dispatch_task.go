package main

import (
	"context"
	"log"

	pb "nexus-swarm/api/proto"
)

// 🛡️ [v22/v24] DispatchTask with Federation Support
func (s *swarmServer) DispatchTask(ctx context.Context, req *pb.DispatchTaskRequest) (*pb.DispatchTaskResponse, error) {
	// 1. 🛡️ Local Dispatch (Priority)
	nodeID := s.selectLocalNode(req)
	if nodeID != "" {
		log.Printf("🛡️ Task %s assigned to local node %s", req.TaskId, nodeID)
		return &pb.DispatchTaskResponse{
			Accepted:       true,
			AssignedNodeId: nodeID,
			Status:         "LOCAL_EXECUTION",
		}, nil
	}

	// 2. 🛡️ Federation Dispatch (Scale-out)
	if federationConfig.EnableFederation {
		peerMu.RLock()
		defer peerMu.RUnlock()

		// 🛡️ Note: PreferredRegion removed from proto in v22, using default.
		targetCluster := selectBestCluster("")
		if targetCluster != "" {
			log.Printf("🛡️ Task %s routing to federation cluster: %s", req.TaskId, targetCluster)
			
			// 🛡️ Simulated Peer Forward (In production we call federationClient.RouteTask)
			return &pb.DispatchTaskResponse{
				Accepted: true,
				Status:   "ROUTED_TO_" + targetCluster,
			}, nil
		}
	}

	return &pb.DispatchTaskResponse{
		Accepted: false,
		Status:   "NO_CAPACITY",
	}, nil
}

// 🛡️ [v22/v24] Simple capacity-based cluster selection (Weighted Round Robin or Least Load)
func selectBestCluster(preferredRegion string) string {
	var bestCluster string
	maxCapacity := int64(0)

	for id, p := range peerClusters {
		if p.AvailableCapacity > maxCapacity {
			if preferredRegion == "" || p.Region == preferredRegion {
				maxCapacity = p.AvailableCapacity
				bestCluster = id
			}
		}
	}

	return bestCluster
}

func (s *swarmServer) selectLocalNode(req *pb.DispatchTaskRequest) string {
	s.mu.Lock()
	defer s.mu.Unlock()

	// 🛡️ 簡單選擇一個健康且有容量的節點
	for id, node := range s.nodes {
		if node.Health == "HEALTHY" && node.ActiveTasks < 10 { // 假設 10 為容量上限
			node.ActiveTasks++
			return id
		}
	}
	return ""
}
