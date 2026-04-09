package index

import (
	"log"
)

// StreamProcessor 處理來自節點的雙向串流審計
type StreamProcessor struct {
	// 這裡可以注入 Graph Engine 或 Rules Engine
}

// HandleSensingStream 處理 SwarmManager.SensingStream 調用 (NSP v0.2)
// 🛡️ Note: Temporarily disabled due to proto drift in v22 branch.
func (p *StreamProcessor) HandleSensingStream(stream interface{}) error {
	log.Println("🌊 [NSP v0.2] SensingStream stubbed (Proto Drift)")
    return nil
}

func isHighRisk(path string) bool {
    // 模擬：如果路徑包含 'script.js'，視為高風險
	return path == "script.js"
}
