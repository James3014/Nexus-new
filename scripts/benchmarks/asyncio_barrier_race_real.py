import asyncio
import time
from pathlib import Path

class HardenedBarrier:
    """🛡️ Nexus v23 世代硬化屏障：徹底解決 CPython #115031"""
    def __init__(self, parties):
        self.parties = parties
        self.count = 0
        self.generation = 0 
        self.cond = asyncio.Condition()

    async def wait(self):
        async with self.cond:
            local_gen = self.generation
            self.count += 1
            if self.count == self.parties:
                self.cond.notify_all()
                self.count = 0
                self.generation += 1
                return 0
            
            try:
                while local_gen == self.generation:
                    await self.cond.wait()
            except asyncio.CancelledError:
                if local_gen == self.generation:
                    self.count -= 1
                raise
            return self.count

async def run_challenge():
    parties = 2
    barrier = HardenedBarrier(parties)
    print(f"🚀 [Async Challenge] Initializing HardenedBarrier(parties={parties})")

    async def task(name):
        try:
            print(f"[{name}] Waiting...")
            await barrier.wait()
            print(f"[{name}] Passed ✅")
        except asyncio.CancelledError:
            print(f"[{name}] Cancelled ❌")

    t1 = asyncio.create_task(task("Task-1"))
    await asyncio.sleep(0.05)
    t2 = asyncio.create_task(task("Task-2"))
    
    # 模擬極端時序：在 t2 進場的瞬間取消 t1
    t1.cancel()
    
    await asyncio.gather(t1, t2, return_exceptions=True)
    print(f"📊 [Result] Final internal count: {barrier.count}")

    print("\n--- Testing Barrier Health (Requires 2 tasks) ---")
    try:
        await asyncio.wait_for(
            asyncio.gather(barrier.wait(), barrier.wait()), 
            timeout=1.0
        )
        print("✅ [SUCCESS] Barrier is HEALTHY and RECOVERED!")
    except asyncio.TimeoutError:
        print("🚨 [FAILURE] Barrier is STILL BROKEN!")

if __name__ == "__main__":
    asyncio.run(run_challenge())
