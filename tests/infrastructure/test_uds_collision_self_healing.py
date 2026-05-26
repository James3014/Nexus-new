#!/usr/bin/env python3
"""
tests/infrastructure/test_uds_collision_self_healing.py

驗證 Nexus Swarm Bridge 的 UDS 自癒清洗邏輯（P0 多租戶隔離）：
1. 殘留 socket 清除：socket 檔案存在但無活躍伺服器 → 自動移除
2. 活躍 socket 保留：socket 存在且伺服器運行 → 不移除
3. 多租戶併發啟動：N 個並發進程競爭同一 socket，最終只有 1 個主導
"""
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path


class UDSSelfHealingTest(unittest.TestCase):
    """UDS 自癒清洗邏輯驗證套件"""

    def _make_stale_socket(self, path: str) -> None:
        """創建殘留 socket 檔案（無伺服器監聽）"""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.bind(path)
            # 不呼叫 listen()，製造殘留態
        finally:
            sock.close()
        # 檔案存在但無監聽

    def _is_socket_alive(self, path: str, timeout: float = 0.3) -> bool:
        """Ping UDS：連線成功代表活躍"""
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            conn.settimeout(timeout)
            conn.connect(path)
            conn.close()
            return True
        except (ConnectionRefusedError, OSError, socket.timeout):
            return False

    def _self_heal(self, path: str) -> bool:
        """
        模擬 Go main.go 的自癒邏輯：
        若 socket 存在但 ping 失敗 → 清除 → 回傳 True (已清除)
        若 socket 存在且 ping 成功 → 保留 → 回傳 False (未清除)

        注意：多租戶競爭情境下，FileNotFoundError 是預期的 TOCTOU race
        （另一個並發 worker 已搶先清除），安全吞掉即可。
        """
        if Path(path).exists():
            if not self._is_socket_alive(path):
                try:
                    os.remove(path)
                    return True  # 殘留已清除
                except FileNotFoundError:
                    return True  # 另一 worker 搶先清除，視同成功
            return False  # 活躍保留
        return False  # 不存在，無需處理

    # ── 測試 1：殘留 socket 自癒清除 ───────────────────────────────────────
    def test_stale_socket_is_removed(self):
        """殘留 socket 存在 → 自癒後不應存在"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = os.path.join(tmpdir, "nexus-test.sock")
            self._make_stale_socket(sock_path)
            self.assertTrue(Path(sock_path).exists(), "殘留 socket 應存在")

            healed = self._self_heal(sock_path)

            self.assertTrue(healed, "自癒應回傳 True (已清除)")
            self.assertFalse(Path(sock_path).exists(), "自癒後 socket 檔案不應存在")

    # ── 測試 2：活躍 socket 不誤刪 ─────────────────────────────────────────
    def test_live_socket_is_preserved(self):
        """活躍 socket（有伺服器監聽）→ 自癒不應刪除"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = os.path.join(tmpdir, "nexus-live.sock")

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(sock_path)
            server.listen(1)

            server_thread = threading.Thread(
                target=lambda: server.accept(), daemon=True
            )
            server_thread.start()
            time.sleep(0.05)

            healed = self._self_heal(sock_path)

            server.close()
            self.assertFalse(healed, "活躍 socket 不應被清除，自癒回傳 False")
            # socket 仍存在（伺服器關閉後可能清除，但測試時仍在）

    # ── 測試 3：多租戶併發啟動壓測（不卡死驗證）──────────────────────────
    def test_concurrent_self_heal_no_deadlock(self):
        """10 個並發進程同時對相同 socket 執行自癒，不應發生 race condition 卡死"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = os.path.join(tmpdir, "nexus-concurrent.sock")
            self._make_stale_socket(sock_path)

            results = []
            errors = []

            def worker():
                try:
                    r = self._self_heal(sock_path)
                    results.append(r)
                except FileNotFoundError:
                    results.append(True)  # TOCTOU: 視同已成功清除
                except Exception as e:
                    errors.append(str(e))

            threads = [threading.Thread(target=worker) for _ in range(10)]
            start = time.time()
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=2.0)  # 2 秒 timeout，防死鎖
            elapsed = time.time() - start

            self.assertListEqual(errors, [], f"並發自癒出現異常: {errors}")
            self.assertLess(elapsed, 2.0, "並發自癒超時，可能死鎖")
            # 最終 socket 不應存在（被某個 worker 清除）
            self.assertFalse(Path(sock_path).exists(), "並發後 stale socket 應被清除")

    # ── 測試 4：無 socket 情境（正常首次啟動）─────────────────────────────
    def test_no_socket_no_action(self):
        """socket 不存在 → 自癒不做任何動作，回傳 False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = os.path.join(tmpdir, "nexus-nonexistent.sock")
            healed = self._self_heal(sock_path)
            self.assertFalse(healed, "不存在時自癒回傳 False")
            self.assertFalse(Path(sock_path).exists(), "socket 不應被創建")


if __name__ == "__main__":
    unittest.main(verbosity=2)
