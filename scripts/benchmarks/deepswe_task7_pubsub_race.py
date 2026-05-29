import threading

class EventBus:
    def __init__(self):
        self._subscribers = None  # Lazy init
        self._lock = threading.Lock()

    def _ensure_initialized(self):
        with self._lock:
            if self._subscribers is None:
                self._subscribers = []

    def subscribe(self, handler):
        self._ensure_initialized()
        with self._lock:
            self._subscribers.append(handler)

    def publish(self, event):
        self._ensure_initialized()
        with self._lock:
            subscribers_copy = list(self._subscribers)
        for handler in subscribers_copy:
            handler(event)

def test_challenge():
    bus = EventBus()
    received = []

    def handler(e):
        received.append(e)

    threads = [threading.Thread(target=bus.subscribe, args=(handler,)) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    bus.publish("test_event")
    assert len(received) == 20, f"Publisher-Subscriber race! Expected 20 handlers but only {len(received)} received the event"