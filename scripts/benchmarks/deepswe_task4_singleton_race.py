import threading
import time

_instance = None

def get_singleton():
    global _instance
    if _instance is None:
        time.sleep(0.001)  # 制造競態視窗
        _instance = {"id": threading.get_ident()}
    return _instance

def test_challenge():
    def worker():
        print(get_singleton())

    threads = []
    for i in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

if __name__ == "__main__":
    print("🚀 Stress Testing...")
    for _ in range(2000): test_challenge()
