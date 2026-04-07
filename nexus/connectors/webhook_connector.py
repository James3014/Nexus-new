import requests
import json
from typing import List
from .base import BaseConnector, NexusEvent

class WebhookConnector(BaseConnector):
    """
    🌐 Webhook Connector (Lowest Coupling)
    職責: 將 Nexus 事件通過 HTTP POST 推送至外部 Webhook (如飛書、Slack、Discord)。
    """
    def __init__(self, url: str, enabled: bool = True):
        self.url = url
        self.enabled = enabled

    def send(self, event: NexusEvent) -> bool:
        if not self.enabled or not self.url:
            return False
            
        payload = event.to_json()
        
        try:
            # 增加 User-Agent 模擬
            headers = {"Content-Type": "application/json", "User-Agent": "Nexus-Singularity-OS/v22"}
            response = requests.post(self.url, data=json.dumps(payload), headers=headers, timeout=5)
            
            if response.status_code < 300:
                print(f"🚀 [Connector:Webhook] Event sent successfully: {event.event_type}")
                return True
            else:
                print(f"⚠️ [Connector:Webhook] Failed to send event. Status: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ [Connector:Webhook] Connection Error: {str(e)}")
            return False

    def poll_commands(self) -> List[str]:
        # Webhook 模式通常是單向推送，暫不支援回調輪詢
        return []
