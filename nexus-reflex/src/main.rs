use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc;
use tokio::time;
use tokio_stream::{wrappers::ReceiverStream, StreamExt};
use tonic::{transport::{Server, Channel}, Request, Response, Status};
use clap::Parser;

pub mod swarm {
    tonic::include_proto!("nexus.swarm.v1");
}

use swarm::swarm_manager_server::{SwarmManager, SwarmManagerServer};
use swarm::swarm_manager_client::SwarmManagerClient;
use swarm::{HeartbeatReq, HeartbeatResp, SensingReq, SensingResp, Metrics};

#[derive(Parser, Debug)]
#[command(author, version, about, long_about = None)]
struct Args {
    #[arg(short, long)]
    id: String,

    #[arg(short, long, default_value = "http://[::1]:8516")]
    manager: String,
}

#[derive(Debug)]
pub struct MySwarmManager {
    node_id: String,
}

#[tonic::async_trait]
impl SwarmManager for MySwarmManager {
    async fn heartbeat(
        &self,
        request: Request<HeartbeatReq>,
    ) -> Result<Response<HeartbeatResp>, Status> {
        let req = request.into_inner();
        println!("💓 [Reflex {}] Manager heartbeat check: {}", self.node_id, req.node_id);
        Ok(Response::new(HeartbeatResp {
            accepted: true,
            sync_timestamp: SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64,
            next_action: "STANDBY".to_string(),
        }))
    }

    type SensingStreamStream = ReceiverStream<Result<SensingResp, Status>>;

    async fn sensing_stream(
        &self,
        request: Request<tonic::Streaming<SensingReq>>,
    ) -> Result<Response<Self::SensingStreamStream>, Status> {
        let mut stream = request.into_inner();
        let (tx, rx) = mpsc::channel(4);
        let node_id = self.node_id.clone();

        tokio::spawn(async move {
            println!("🌊 [Reflex {}] New SensingStream established", node_id);
            while let Some(req_result) = stream.next().await {
                if let Ok(req) = req_result {
                    let resp = SensingResp {
                        node_id: node_id.clone(),
                        status: "PASS".to_string(),
                        summary: format!("Audit PASS for {}", req.path),
                        metrics: Some(Metrics {
                            selection_latency_us: 150,
                            network_latency_ms: 10,
                            execution_ms: 45,
                            region: "asia-east1".to_string(),
                            confidence_score: 0.99,
                        }),
                        ..Default::default()
                    };
                    if tx.send(Ok(resp)).await.is_err() { break; }
                }
            }
        });
        Ok(Response::new(ReceiverStream::new(rx)))
    }

    async fn sensing(
        &self,
        request: Request<SensingReq>,
    ) -> Result<Response<SensingResp>, Status> {
        Ok(Response::new(SensingResp {
            node_id: self.node_id.clone(),
            status: "PASS".to_string(),
            summary: "Unary Sensing Complete".to_string(),
            ..Default::default()
        }))
    }
}

async fn start_heartbeat_loop(node_id: String, manager_addr: String) {
    let mut interval = time::interval(Duration::from_secs(5));
    println!("💓 [Reflex {}] Starting heartbeat loop to {}", node_id, manager_addr);
    
    loop {
        interval.tick().await;
        let mut client = match SwarmManagerClient::connect(manager_addr.clone()).await {
            Ok(c) => c,
            Err(_) => {
                eprintln!("⚠️ [Reflex {}] Failed to connect to manager", node_id);
                continue;
            }
        };

        let req = Request::new(HeartbeatReq {
            node_id: node_id.clone(),
            status: "ONLINE".to_string(),
            timestamp: SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64,
            capabilities: vec!["sensing".to_string(), "audit".to_string()],
        });

        if let Err(e) = client.heartbeat(req).await {
            eprintln!("❌ [Reflex {}] Heartbeat failed: {}", node_id, e);
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = Args::parse();
    
    // 根據 ID 分配監聽埠 (例如 node-1 -> 8521)
    let node_num: u16 = args.id.strip_prefix("node-").and_then(|s| s.parse().ok()).unwrap_or(0);
    let listen_addr = format!("[::1]:{}", 8520 + node_num).parse()?;
    
    let node_id = args.id.clone();
    let manager_addr = args.manager.clone();

    // 💓 啟動主動心跳任務
    tokio::spawn(async move {
        start_heartbeat_loop(node_id, manager_addr).await;
    });

    println!("🚀 [Nexus Reflex] Node {} starting on {}", args.id, listen_addr);

    let swarm_manager = MySwarmManager { node_id: args.id };
    Server::builder()
        .add_service(SwarmManagerServer::new(swarm_manager))
        .serve(listen_addr)
        .await?;

    Ok(())
}
