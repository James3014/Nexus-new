import subprocess
import logging
import os
import shlex

logger = logging.getLogger(__name__)

class NexusNotifier:
    """
    📢 Nexus 告警與通知核心 (Phase N)
    實施 macOS 物理系統彈窗、終端 HUD 刷新與全域語音告警。
    """
    
    @staticmethod
    def notify(title: str, message: str, level: str = "INFO"):
        """🎯 綜合通知矩陣發動"""
        logger.info(f"📢 [Notifier:{level}] {title}: {message}")
        
        # 1. 物理系統通知 (macOS)
        if level in ["WARNING", "CRITICAL"]:
            NexusNotifier._system_ui_notify(title, message)
            
        # 2. 全域語音告警 (macOS say)
        if level == "CRITICAL":
            NexusNotifier._voice_alert(f"NEXUS {title} 偵測到嚴重異常，請審核行動。")

    @staticmethod
    def _system_ui_notify(title: str, message: str):
        """🍎 macOS osascript 物理彈窗"""
        script = f'display notification "{message}" with title "🛡️ Nexus {title}"'
        try:
            subprocess.run(["osascript", "-e", script], check=True)
        except Exception as e:
            logger.error(f"❌ [Notifier:UI] Failed to trigger notification: {e}")

    @staticmethod
    def _voice_alert(text: str):
        """🔊 Nexus 全域語音告警 (符合 Nexus 戰甲規範)"""
        # 使用 nohup 並導向 /dev/null 以免阻塞
        # 遵循全域規則：nohup say "..." > /dev/null 2>&1 &
        cmd = f'nohup say {shlex.quote(text)} > /dev/null 2>&1 &'
        try:
            subprocess.Popen(cmd, shell=True)  # nosec B602
        except Exception as e:
            logger.error(f"❌ [Notifier:Voice] Failed to trigger voice alert: {e}")

if __name__ == "__main__":
    # 測試執行
    NexusNotifier.notify("Sentinel", "測試通知：治理指標正常", level="INFO")
    # NexusNotifier.notify("Alert", "偵測到 Regression!", level="CRITICAL")
