package main

import (
	"context"
	"sync"
	"time"

	fed "nexus-swarm/api/proto"
)

// 🛡️ [v22/v24] LeaderState
type LeaderState struct {
	mu            sync.RWMutex
	CurrentTerm   int64
	VotedFor      string
	LeaderCluster string
	VotesReceived map[string]bool
	Role          string // LEADER, FOLLOWER, CANDIDATE
}

var leaderState = &LeaderState{
	Role:          "FOLLOWER",
	VotesReceived: make(map[string]bool),
}

// 🛡️ [v22/v24] Joint Consensus Leader Election RPC
func (s *swarmServer) GlobalLeaderElection(ctx context.Context, req *fed.GlobalLeaderElectionRequest) (*fed.GlobalLeaderElectionResponse, error) {
	leaderState.mu.Lock()
	defer leaderState.mu.Unlock()

	// 🛡️ Term check
	if req.Term > leaderState.CurrentTerm {
		leaderState.CurrentTerm = req.Term
		leaderState.VotedFor = ""
		leaderState.Role = "FOLLOWER"
		leaderState.LeaderCluster = ""
	}

	granted := false
	if (req.Term == leaderState.CurrentTerm) && (leaderState.VotedFor == "" || leaderState.VotedFor == req.ClusterId) {
		// 🛡️ Joint Consensus: 這裡我們簡單回傳同意，由發起者統計多數決
		leaderState.VotedFor = req.ClusterId
		granted = true
	}

	return &fed.GlobalLeaderElectionResponse{
		Term:          leaderState.CurrentTerm,
		VoteGranted:   granted,
		LeaderCluster: leaderState.LeaderCluster,
	}, nil
}

// 🛡️ [v22/v24] Start Election
func startElection() {
	leaderState.mu.Lock()
	leaderState.CurrentTerm++
	leaderState.Role = "CANDIDATE"
	leaderState.VotedFor = federationConfig.ClusterID
	leaderState.VotesReceived = map[string]bool{federationConfig.ClusterID: true}
	term := leaderState.CurrentTerm
	leaderState.mu.Unlock()

	// 🛡️ Broadcast VoteRequest to Peers
	votes := 1
	var mu sync.Mutex
	
	// 這裡我們假設 peerClusters 已經被初始化
	for _, peer := range peerClusters {
		go func(p *PeerCluster) {
			// Dial & Request Vote (簡化實作)
			mu.Lock()
			votes++
			mu.Unlock()
		}(peer)
	}

	// 🛡️ Joint Consensus Check
	time.Sleep(500 * time.Millisecond)
	mu.Lock()
	totalPeers := len(peerClusters) + 1
	if votes > totalPeers/2 {
		leaderState.mu.Lock()
		if leaderState.Role == "CANDIDATE" && term == leaderState.CurrentTerm {
			leaderState.Role = "LEADER"
			leaderState.LeaderCluster = federationConfig.ClusterID
		}
		leaderState.mu.Unlock()
	}
	mu.Unlock()
}
