package main

import (
    "database/sql"
    "fmt"
    "log"
    "time"

    _ "github.com/lib/pq"
)

type DB struct {
    *sql.DB
}

func NewDB(dsn string) (*DB, error) {
    // 🛡️ Retry logic for K8s startup (waiting for Postgres)
    var db *sql.DB
    var err error
    for i := 0; i < 10; i++ {
        db, err = sql.Open("postgres", dsn)
        if err == nil {
            if err = db.Ping(); err == nil {
                break
            }
        }
        log.Printf("[DB] Waiting for PostgreSQL (attempt %d)...", i+1)
        time.Sleep(5 * time.Second)
    }

    if err != nil {
        return nil, fmt.Errorf("failed to connect to db after retries: %w", err)
    }

    // 🛡️ [v22/v24] Initial Schema
    _, err = db.Exec(`
        CREATE TABLE IF NOT EXISTS nodes (
            node_id VARCHAR(64) PRIMARY KEY,
            region VARCHAR(32) NOT NULL,
            cpu_percent DOUBLE PRECISION DEFAULT 0,
            memory_percent DOUBLE PRECISION DEFAULT 0,
            active_tasks INTEGER DEFAULT 0,
            health VARCHAR(32) DEFAULT 'UNKNOWN',
            advertise_addr VARCHAR(128),
            last_seen TIMESTAMPTZ DEFAULT NOW(),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_nodes_region ON nodes(region);
        CREATE INDEX IF NOT EXISTS idx_nodes_last_seen ON nodes(last_seen);
    `)
    if err != nil {
        return nil, fmt.Errorf("init schema: %w", err)
    }

    log.Println("[DB] PostgreSQL initialized successfully.")
    return &DB{db}, nil
}

func (db *DB) UpsertNode(nodeID, region, health, addr string, cpu, mem float64, tasks int) error {
    _, err := db.Exec(`
        INSERT INTO nodes (node_id, region, cpu_percent, memory_percent, active_tasks, health, advertise_addr, last_seen)
        VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        ON CONFLICT (node_id) DO UPDATE SET
            cpu_percent = EXCLUDED.cpu_percent,
            memory_percent = EXCLUDED.memory_percent,
            active_tasks = EXCLUDED.active_tasks,
            health = EXCLUDED.health,
            advertise_addr = EXCLUDED.advertise_addr,
            last_seen = NOW()
    `, nodeID, region, cpu, mem, tasks, health, addr)
    return err
}

func (db *DB) GetClusterSummary() ([]map[string]interface{}, error) {
    rows, err := db.Query(`
        SELECT node_id, region, cpu_percent, memory_percent, active_tasks, health
        FROM nodes
        WHERE last_seen > NOW() - INTERVAL '120 seconds'
        ORDER BY last_seen DESC
    `)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var nodes []map[string]interface{}
    for rows.Next() {
        var nodeID, region, health string
        var cpu, mem float64
        var tasks int
        if err := rows.Scan(&nodeID, &region, &cpu, &mem, &tasks, &health); err != nil {
            return nil, err
        }
        nodes = append(nodes, map[string]interface{}{
            "node_id":       nodeID,
            "region":        region,
            "cpu_percent":   cpu,
            "memory_percent": mem,
            "active_tasks":  tasks,
            "health":        health,
        })
    }
    return nodes, nil
}
