package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"nexus-swarm/pkg/index"

	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type Node struct {
	URL    string
	Region string
}

type SensingRequest struct {
	RepoURL    string `json:"repo_url"`
	Path       string `json:"path"`
	BaseCommit string `json:"base_commit"`
	TaskType   string `json:"task_type"`
	TaskKey    string `json:"task_key"`
}

type Metrics struct {
	SelectionLatencyUS int64  `json:"selection_latency_us"`
	NetworkLatencyMS   int64  `json:"network_latency_ms"`
	ExecutionMS        int64  `json:"execution_ms"`
	Region             string `json:"region"`
}

type DiagnosticReport struct {
	NodeID  string  `json:"node_id"`
	Status  string  `json:"status"`
	Summary string  `json:"summary"`
	Metrics Metrics `json:"metrics"`
	Error   string  `json:"error,omitempty"`
}

func main() {
	fmt.Println("🚀 Nexus-Go Swarm Manager (v19.1 Durable Control Plane) Starting...")

	dbPath := "swarm_tasks.db"
	pe := index.NewPersistenceEngine(dbPath)
	stalled := pe.RecoverStalledTasks()
	if stalled > 0 {
		fmt.Printf("♻️  [Recovery] Successfully recovered %d stalled tasks.\n", stalled)
	}

	token := os.Getenv("NEXUS_SWARM_TOKEN")
	
	// 動態載入節點拓樸
	nodesData, err := ioutil.ReadFile("nodes.json")
	var nodes []Node
	if err == nil {
		json.Unmarshal(nodesData, &nodes)
	}
	if len(nodes) == 0 {
		fmt.Println("⚠️  Warning: nodes.json is empty or missing. Using default local node.")
		nodes = []Node{{URL: "http://localhost:8001", Region: "us-east-1"}}
	}
	fmt.Printf("🐝 [Topology] Loaded %d nodes from nodes.json\n", len(nodes))

	// 模擬新任務
	rootTask := &index.TaskRecord{
		ID:           "global_audit_v19",
		RepoURL:      "https://github.com/nexus/core",
		Path:         "repo_root",
		Status:       index.StatusPending,
		AttemptCount: 0,
	}
	pe.SaveTask(rootTask)
	pe.EnqueuePending(rootTask.ID)
	fmt.Printf("📥 [Queue] Enqueued root task %s.\n", rootTask.ID)

	// 啟動 Prometheus Metrics Server (v24 SRE Hardening)
	metricsPort := os.Getenv("NEXUS_METRICS_PORT")
	if metricsPort == "" {
		metricsPort = "9100"
	}
	go func() {
		fmt.Printf("📊 Prometheus metrics available at :%s/metrics\n", metricsPort)
		http.Handle("/metrics", promhttp.Handler())
		http.ListenAndServe(":"+metricsPort, nil)
	}()

	// 緊急降級檢查 (Fail-Open)
	if os.Getenv("NEXUS_GATE_BYPASS") == "true" {
		fmt.Println("⚠️  [EMERGENCY] NEXUS_GATE_BYPASS=true. Fail-Open mode activated.")
	}

	// 消費任務隊列 (Producer-Consumer v0.2.1)
	var wg sync.WaitGroup
	managerRegion := "us-east-1"

	// 啟動一個監聽隊列的派發器
	go func() {
		for id := range pe.PendingQueue {
			// Bypass logic: if bypass is on, we skip processing but the audit might need a shell manager
			// For simplicity, we process anyway but wouldn't fail the CI gate in a real script.

			wg.Add(1)
			go func(tid string) {
				defer wg.Done()
				
				// 1. Fetch Task from Actor
				t, ok := pe.GetTask(tid)
				if !ok || t.Status != index.StatusPending {
					return
				}

				// Generate TraceID
				t.TraceID = fmt.Sprintf("trace-%d-%s", time.Now().UnixNano(), tid)

				// 2. Span: Selection
				selectStart := time.Now()
				bestNode := getBestNode(nodes, t.Path)
				selectDuration := time.Since(selectStart)
				index.MetricTaskLatency.WithLabelValues("selection").Observe(selectDuration.Seconds())
				fmt.Printf("📊 [SPAN:selection] trace_id=%s task_id=%s duration_us=%d node_url=%s region=%s\n",
					t.TraceID, tid, selectDuration.Microseconds(), bestNode.URL, bestNode.Region)

				// 3. Mark Running & Lease
				t.Status = index.StatusRunning
				t.LeaseExpiresAt = time.Now().Add(30 * time.Second)
				pe.SaveTask(t)

				// 3. Span: Network (Simulated)
				netStart := time.Now()
				netLatency := getLatency(managerRegion, bestNode.Region)
				time.Sleep(netLatency) // Simulate RTT
				netDuration := time.Since(netStart)
				index.MetricTaskLatency.WithLabelValues("network").Observe(netDuration.Seconds())
				fmt.Printf("📊 [SPAN:network] trace_id=%s task_id=%s duration_ms=%d from=%s to=%s\n",
					t.TraceID, tid, netDuration.Milliseconds(), managerRegion, bestNode.Region)

				// 4. Span: Execution
				execStart := time.Now()
				report, err := dispatchTask(bestNode.URL, t, token)
				execDuration := time.Since(execStart)
				index.MetricTaskLatency.WithLabelValues("execution").Observe(execDuration.Seconds())

				if err != nil {
					fmt.Printf("❌ [Error] Task %s failed: %v\n", tid, err)
					t.Status = index.StatusFailed
					pe.SaveTask(t)
					index.MetricTasksFailed.Inc()
					return
				}

				fmt.Printf("📊 [SPAN:execution] trace_id=%s task_id=%s duration_ms=%d node_id=%s status=%s\n",
					t.TraceID, tid, execDuration.Milliseconds(), report.NodeID, report.Status)

				// 5. Finalize
				t.Status = index.StatusDone
				t.Summary = report.Summary
				pe.SaveTask(t)
				index.MetricTasksProcessed.Inc()
			}(id)
		}
	}()

	// 模式：監聽模式，直到收到中斷信號 (Audit 腳本會負責終止)
	fmt.Println("🛰️  Manager is in Listening Mode. Waiting for tasks...")
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM, syscall.SIGINT)
	<-stop

	fmt.Println("\n✨ Swarm Fleet Operation Window Closed.")
}

var rrCounter uint64

func getBestNode(nodes []Node, targetRegion string) Node {
	var candidates []Node
	for _, n := range nodes {
		if n.Region == targetRegion {
			candidates = append(candidates, n)
		}
	}
	
	if len(candidates) == 0 {
		candidates = nodes
	}
	
	// Atomic Round-Robin
	idx := atomic.AddUint64(&rrCounter, 1) % uint64(len(candidates))
	return candidates[idx]
}

func getLatency(from, to string) time.Duration {
	if from == to {
		return 5 * time.Millisecond
	}
	// 模擬真實雲端延遲矩陣
	matrix := map[string]time.Duration{
		"us-east-1_eu-west-1":      90 * time.Millisecond,
		"us-east-1_ap-northeast-1": 220 * time.Millisecond,
	}
	key := from + "_" + to
	if lat, ok := matrix[key]; ok {
		return lat
	}
	return 150 * time.Millisecond
}

func dispatchTask(nodeURL string, task *index.TaskRecord, token string) (DiagnosticReport, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// W3C Trace Context formatting: 00-traceid-spanid-flags
	// Using the existing TraceID, assuming it's correctly formatted or using it as the core.
	traceParent := fmt.Sprintf("00-%s-00f067aa0ba902b7-01", task.TraceID[6:]) // slice "trace-" prefix

	reqPayload := SensingRequest{
		RepoURL:  task.RepoURL,
		Path:     task.Path,
		TaskKey:  task.ID,
		TaskType: "L6_AUDIT",
	}

	jsonData, _ := json.Marshal(reqPayload)
	req, _ := http.NewRequestWithContext(ctx, "POST", nodeURL+"/sensing", bytes.NewBuffer(jsonData))
	req.Header.Set("X-Nexus-Token", token)
	req.Header.Set("traceparent", traceParent)
	req.Header.Set("Content-Type", "application/json")

	client := &http.Client{}
	resp, err := client.Do(req)
	if err != nil {
		return DiagnosticReport{}, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return DiagnosticReport{}, fmt.Errorf("node returned %d", resp.StatusCode)
	}

	body, _ := ioutil.ReadAll(resp.Body)
	var report DiagnosticReport
	err = json.Unmarshal(body, &report)
	return report, err
}
