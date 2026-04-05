package index

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"os"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	MetricTasksProcessed = promauto.NewCounter(prometheus.CounterOpts{
		Name: "nexus_tasks_processed_total",
		Help: "Total number of tasks processed by the swarm",
	})
	MetricTasksFailed = promauto.NewCounter(prometheus.CounterOpts{
		Name: "nexus_tasks_failed_total",
		Help: "Total number of failed tasks",
	})
	MetricTaskLatency = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "nexus_task_latency_seconds",
		Help:    "Latency of tasks in seconds bucketed by stage",
		Buckets: prometheus.DefBuckets,
	}, []string{"stage"})
)

type TaskStatus string

const (
	StatusPending TaskStatus = "PENDING"
	StatusRunning TaskStatus = "RUNNING"
	StatusDone    TaskStatus = "DONE"
	StatusFailed  TaskStatus = "FAILED"
)

type TaskRecord struct {
	ID              string     `json:"id"`
	TraceID         string     `json:"trace_id"`
	RepoURL         string     `json:"repo_url"`
	Path            string     `json:"path"`
	Status          TaskStatus `json:"status"`
	PreviousState   TaskStatus `json:"previous_state,omitempty"`
	AttemptCount    int        `json:"attempt_count"`
	LeaseExpiresAt  time.Time  `json:"lease_expires_at"`
	LastHeartbeatAt time.Time  `json:"last_heartbeat_at"`
	Summary         string     `json:"summary,omitempty"`
}

type Action string

const (
	ActionSave    Action = "SAVE"
	ActionGet     Action = "GET"
	ActionRecover Action = "RECOVER"
)

type Command struct {
	Type   Action
	Task   *TaskRecord
	TaskID string
	Resp   chan *TaskRecord
	Err    chan error
}

type PersistenceEngine struct {
	dbPath       string
	tasks        map[string]*TaskRecord
	dirty        bool
	cmdChan      chan Command
	PendingQueue chan string
}

func NewPersistenceEngine(path string) *PersistenceEngine {
	pe := &PersistenceEngine{
		dbPath:       path,
		tasks:        make(map[string]*TaskRecord),
		cmdChan:      make(chan Command, 5000),
		PendingQueue: make(chan string, 5000),
	}
	pe.LoadAll()
	go pe.runActor()
	return pe
}

func (pe *PersistenceEngine) EnqueuePending(id string) {
	pe.PendingQueue <- id
}

func (pe *PersistenceEngine) SaveTask(t *TaskRecord) error {
	errCh := make(chan error, 1)
	pe.cmdChan <- Command{Type: ActionSave, Task: t, Err: errCh}
	return <-errCh
}

func (pe *PersistenceEngine) GetTask(id string) (*TaskRecord, bool) {
	resp := make(chan *TaskRecord, 1)
	pe.cmdChan <- Command{Type: ActionGet, TaskID: id, Resp: resp}
	t := <-resp
	return t, t != nil
}

func (pe *PersistenceEngine) RecoverStalledTasks() int {
	errCh := make(chan error, 1) // Using Err chan to transport count hackily or just update status
	pe.cmdChan <- Command{Type: ActionRecover, Err: errCh}
	<-errCh
	return 0 // Count handled internally in actor logs
}

func (pe *PersistenceEngine) runActor() {
	ticker := time.NewTicker(500 * time.Millisecond)
	for {
		select {
		case cmd := <-pe.cmdChan:
			switch cmd.Type {
			case ActionSave:
				pe.tasks[cmd.Task.ID] = cmd.Task
				pe.dirty = true
				if cmd.Err != nil {
					cmd.Err <- nil
				}
			case ActionGet:
				t, ok := pe.tasks[cmd.TaskID]
				if ok && cmd.Resp != nil {
					cmd.Resp <- t
				} else if cmd.Resp != nil {
					cmd.Resp <- nil
				}
			case ActionRecover:
				count := 0
				now := time.Now()
				for _, t := range pe.tasks {
					if t.Status == StatusRunning && now.After(t.LeaseExpiresAt) {
						t.Status = StatusPending
						t.AttemptCount++
						// Async push to avoid deadlock with Actor (v23.2 Fix)
						go func(id string) {
							pe.PendingQueue <- id
						}(t.ID)
						count++
						fmt.Printf("📢 [EVENT:task.recovered] task_id=%s\n", t.ID)
					}
				}
				if count > 0 {
					pe.dirty = true
				}
				if cmd.Err != nil {
					cmd.Err <- nil
				}
			}
		case <-ticker.C:
			if pe.dirty {
				// Snapshot for non-blocking flush
				snapshot := make(map[string]*TaskRecord)
				for k, v := range pe.tasks {
					snapshot[k] = v
				}
				pe.dirty = false
				
				go func(data map[string]*TaskRecord) {
					pe.flushTasks(data)
				}(snapshot)
			}
		}
	}
}

func (pe *PersistenceEngine) flushTasks(tasks map[string]*TaskRecord) error {
	data, _ := json.MarshalIndent(tasks, "", "  ")
	tmpPath := pe.dbPath + ".tmp"
	ioutil.WriteFile(tmpPath, data, 0644)
	return os.Rename(tmpPath, pe.dbPath)
}

func (pe *PersistenceEngine) LoadAll() error {
	if _, err := os.Stat(pe.dbPath); os.IsNotExist(err) {
		return nil
	}
	data, err := ioutil.ReadFile(pe.dbPath)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(data, &pe.tasks); err != nil {
		return err
	}
	for id, t := range pe.tasks {
		if t.Status == StatusPending {
			pe.PendingQueue <- id
		}
	}
	return nil
}
