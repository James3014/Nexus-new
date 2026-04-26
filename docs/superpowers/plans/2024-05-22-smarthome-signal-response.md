# SmartHome Signal Response Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a Python 'SmartHome' system where multiple async devices react to a 'Home' event simultaneously without global state coupling.

**Architecture:** Following the "Signal Response" insight from V8-Candidate '楊定一寫碼聖衣'. Devices are independent observers that subscribe to a central signal hub. The hub is stateless regarding device internal states, merely facilitating the propagation of signals.

**Tech Stack:** Python 3.10, `asyncio`.

---

### Task 1: Core Signal Infrastructure

**Files:**
- Create: `smarthome_signal.py`

- [ ] **Step 1: Define SignalHub and Device Interface**
Implement the `SignalHub` that manages a list of async callbacks and a `Device` base class.

```python
import asyncio
from typing import Callable, Coroutine, List, Any

class SignalHub:
    def __init__(self):
        self._observers: List[Callable[[str, Any], Coroutine[Any, Any, None]]] = []

    def subscribe(self, observer: Callable[[str, Any], Coroutine[Any, Any, None]]):
        self._observers.append(observer)

    async def emit(self, event: str, data: Any = None):
        # Simultaneous broadcast without waiting for each sequentially
        await asyncio.gather(*(observer(event, data) for observer in self._observers))

class Device:
    def __init__(self, name: str, hub: SignalHub):
        self.name = name
        hub.subscribe(self.on_signal)

    async def on_signal(self, event: str, data: Any):
        pass
```

### Task 2: Concrete Devices

**Files:**
- Modify: `smarthome_signal.py`

- [ ] **Step 1: Implement SmartLight**
```python
class SmartLight(Device):
    async def on_signal(self, event: str, data: Any):
        if event == "HOME":
            print(f"[Light] {self.name} is turning on gracefully...")
            await asyncio.sleep(0.5)
            print(f"[Light] {self.name} is ON.")
```

- [ ] **Step 2: Implement AirConditioner**
```python
class AirConditioner(Device):
    async def on_signal(self, event: str, data: Any):
        if event == "HOME":
            print(f"[AC] {self.name} is setting temperature to 24°C...")
            await asyncio.sleep(0.8)
            print(f"[AC] {self.name} is COOLING.")
```

- [ ] **Step 3: Implement SecuritySystem**
```python
class SecuritySystem(Device):
    async def on_signal(self, event: str, data: Any):
        if event == "HOME":
            print(f"[Security] {self.name} is disarming sensors...")
            await asyncio.sleep(0.3)
            print(f"[Security] {self.name} is DISARMED.")
```

### Task 3: Integration and Demo

**Files:**
- Modify: `smarthome_signal.py`

- [ ] **Step 1: Add Main Entry Point**
```python
async def main():
    import time
    start_time = time.perf_counter()
    
    hub = SignalHub()
    
    # Instantiate devices - they subscribe themselves
    light = SmartLight("Living Room Light", hub)
    ac = AirConditioner("Main AC", hub)
    security = SecuritySystem("Home Guard", hub)
    
    print("--- Event: HOME Triggered ---")
    await hub.emit("HOME")
    
    end_time = time.perf_counter()
    print(f"--- All devices reacted in {end_time - start_time:.4f} seconds ---")

if __name__ == "__main__":
    asyncio.run(main())
```

### Task 4: Verification

- [ ] **Step 1: Run the script and verify concurrency**
The total time should be close to the maximum sleep time (0.8s) rather than the sum (1.6s).
