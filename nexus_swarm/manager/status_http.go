package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"
)

func startHTTPServer(s *swarmServer) {
	mux := http.NewServeMux()

	// JSON Status for Nexus Desk
	mux.HandleFunc("/cluster/status", func(w http.ResponseWriter, r *http.Request) {
		status, err := s.GetClusterStatus(r.Context(), nil)
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		// Enable CORS for web mode
		w.Header().Set("Access-Control-Allow-Origin", "*")
		json.NewEncoder(w).Encode(status)
	})

	// Prometheus Metrics for SRE Runbook compliance
	mux.HandleFunc("/metrics", func(w http.ResponseWriter, r *http.Request) {
		status, _ := s.GetClusterStatus(r.Context(), nil)
		
		w.Header().Set("Content-Type", "text/plain")
		
		fmt.Fprintln(w, "# HELP nexusswarmhealthynodes Total healthy nodes in the swarm")
		fmt.Fprintln(w, "# TYPE nexusswarmhealthynodes gauge")
		fmt.Fprintf(w, "nexusswarmhealthynodes %d\n", status.HealthyNodes)
		
		for _, node := range status.Nodes {
			fmt.Fprintf(w, "nexusnodecpu{node_id=\"%s\",region=\"%s\"} %f\n", node.NodeId, node.Region, node.CpuPercent)
			fmt.Fprintf(w, "nexusnodememory{node_id=\"%s\",region=\"%s\"} %f\n", node.NodeId, node.Region, node.MemoryPercent)
		}
	})

	srv := &http.Server{
		Addr:         ":9100",
		Handler:      mux,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
	}

	log.Printf("[NEXUS v22] HTTP Status listening on :9100")
	if err := srv.ListenAndServe(); err != nil {
		log.Printf("[ERROR] HTTP Server failed: %v", err)
	}
}
