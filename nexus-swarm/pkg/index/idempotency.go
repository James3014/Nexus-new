package index

import (
	"sync"
)

// IdempotencyEngine tracks task execution to prevent redundant work.
// It uses TaskStatus from persistence.go for consistency.
type IdempotencyEngine struct {
	mu    sync.RWMutex
	tasks map[string]TaskStatus
}

func NewIdempotencyEngine() *IdempotencyEngine {
	return &IdempotencyEngine{
		tasks: make(map[string]TaskStatus),
	}
}

func (e *IdempotencyEngine) TryStart(key string) bool {
	e.mu.Lock()
	defer e.mu.Unlock()

	status, exists := e.tasks[key]
	if exists && (status == StatusRunning || status == StatusDone) {
		return false
	}

	e.tasks[key] = StatusRunning
	return true
}

func (e *IdempotencyEngine) Complete(key string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.tasks[key] = StatusDone
}

func (e *IdempotencyEngine) Fail(key string) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.tasks[key] = StatusFailed
}

func (e *IdempotencyEngine) GetStatus(key string) TaskStatus {
	e.mu.RLock()
	defer e.mu.RUnlock()
	if s, ok := e.tasks[key]; ok {
		return s
	}
	return StatusPending
}
