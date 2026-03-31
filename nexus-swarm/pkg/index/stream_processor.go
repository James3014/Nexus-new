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

// HandleSensingStream 處理 SwarmManager.SensingStream 調用 (NSP v0.2)
func (p *StreamProcessor) HandleSensingStream(stream pb.SwarmManager_SensingStreamServer) error {
	log.Println("🌊 [NSP v0.2] New SensingStream connection established")

	for {
		// 1. 接收分片請求
		req, err := stream.Recv()
		if err == io.EOF {
			log.Println("✅ [NSP v0.2] SensingStream finished successfully")
			return nil
		}
		if err != nil {
			log.Printf("❌ [NSP v0.2] SensingStream error: %v", err)
			return err
		}

		log.Printf("📥 [NSP v0.2] Received chunk for task: %s", req.TaskId)

		// 2. 進行局部即時分析 (Mock Logic)
		if isHighRisk(req.Path) {
			resp := &pb.SensingResp{
				NodeId:  "MANAGER_PRIMARY",
				Status:  "HIGH_RISK_ALERT",
				Summary: "🚨 Real-time alert: Schema-UI binding detected in current chunk!",
			}
			// 3. 即時回傳診斷報告
			if err := stream.Send(resp); err != nil {
				return err
			}
			log.Println("🔔 [NSP v0.2] Instant sensing response sent back to node")
		}
	}
}

func isHighRisk(path string) bool {
    // 模擬：如果路徑包含 'script.js'，視為高風險
	return path == "script.js"
}
