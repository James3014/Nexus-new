package index

import (
	"io"
	"log"
	pb "nexus-swarm/api/proto"
)

// StreamProcessor 處理來自節點的雙向串流審計
type StreamProcessor struct {
	// 這裡可以注入 Graph Engine 或 Rules Engine
}

// HandleStreamAudit 處理 SensingService.StreamAudit 調用
func (p *StreamProcessor) HandleStreamAudit(stream pb.SensingService_StreamAuditServer) error {
	log.Println("🌊 [NSP] New StreamAudit connection established")

	for {
		// 1. 接收分片請求
		req, err := stream.Recv()
		if err == io.EOF {
			log.Println("✅ [NSP] StreamAudit finished successfully")
			return nil
		}
		if err != nil {
			log.Printf("❌ [NSP] StreamAudit error: %v", err)
			return err
		}

		log.Printf("📥 [NSP] Received chunk for task: %s", req.TaskId)

		// 2. 進行局部即時分析 (Mock Logic)
		// 假設在這裡觸發 Fragility Check
		if isHighRisk(req.Path) {
			report := &pb.DiagnosticReport{
				NodeId:  "MANAGER_PRIMARY",
				Status:  "HIGH_RISK_ALERT",
				Summary: "🚨 Real-time alert: Schema-UI binding detected in current chunk!",
			}
			// 3. 即時回傳診斷報告
			if err := stream.Send(report); err != nil {
				return err
			}
			log.Println("🔔 [NSP] Instant diagnostic report sent back to node")
		}
	}
}

func isHighRisk(path string) bool {
    // 模擬：如果路徑包含 'script.js'，視為高風險
	return path == "script.js"
}
