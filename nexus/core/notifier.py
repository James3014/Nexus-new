import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def _side_effects_suppressed() -> bool:
    """True under pytest or when NEXUS_NOTIFIER_SILENT=1 (covers subprocesses and CI)."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) or os.environ.get(
        "NEXUS_NOTIFIER_SILENT", ""
    ).strip() in {"1", "true", "True"}


# #2635 SEC-006: title and message travel as osascript argv items read by
# ``on run argv``; they are never spliced into AppleScript source, so a quote
# in a file name or message cannot inject AppleScript (e.g. ``do shell script``).
_NOTIFICATION_SCRIPT = (
    "on run argv\ndisplay notification (item 2 of argv) with title (item 1 of argv)\nend run"
)


def build_notification_argv(title: str, message: str) -> list[str]:
    """Return the osascript argv that shows *message* without code injection."""
    return ["osascript", "-e", _NOTIFICATION_SCRIPT, f"🛡️ Nexus {title}", str(message)]


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
        if _side_effects_suppressed():
            return
        try:
            subprocess.run(build_notification_argv(title, message), check=True)
        except Exception as e:
            logger.error(f"❌ [Notifier:UI] Failed to trigger notification: {e}")

    @staticmethod
    def _voice_alert(text: str):
        """🔊 Nexus 全域語音告警 (符合 Nexus 戰甲規範)"""
        if _side_effects_suppressed():
            return
        # 背景執行、輸出導向 /dev/null 以免阻塞 (#2635: argv, no shell)
        try:
            subprocess.Popen(
                ["say", str(text)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as e:
            logger.error(f"❌ [Notifier:Voice] Failed to trigger voice alert: {e}")


if __name__ == "__main__":
    # 測試執行
    NexusNotifier.notify("Sentinel", "測試通知：治理指標正常", level="INFO")
    # NexusNotifier.notify("Alert", "偵測到 Regression!", level="CRITICAL")
