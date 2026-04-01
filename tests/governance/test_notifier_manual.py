from nexus.core.notifier import NexusNotifier
import time

def test_manual_notifications():
    print("🚀 [ManualTest] Launching Notification Matrix...")
    
    # 1. INFO級別：僅 Log
    print("  -> INFO: Logging only...")
    NexusNotifier.notify("Test", "This is an INFO log.", level="INFO")
    time.sleep(1)
    
    # 2. WARNING級別：Log + macOS UI Notification
    print("  -> WARNING: UI Notification expected...")
    NexusNotifier.notify("Warning", "Detected staged changes!", level="WARNING")
    time.sleep(2)
    
    # 3. CRITICAL級別：Log + UI + Voice Alert
    print("  -> CRITICAL: UI + Voice expected...")
    NexusNotifier.notify("CRITICAL", "Regression detected!", level="CRITICAL")

if __name__ == "__main__":
    test_manual_notifications()
