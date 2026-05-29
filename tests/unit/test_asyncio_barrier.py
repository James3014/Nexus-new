import pytest
import asyncio
import scripts.benchmarks.asyncio_barrier_race_real as b

@pytest.mark.asyncio
async def test_asyncio_barrier_cancellation_race():
    parties = 2
    barrier = b.HardenedBarrier(parties)
    
    async def task(name):
        try:
            await barrier.wait()
        except asyncio.CancelledError:
            raise

    t1 = asyncio.create_task(task("Task-1"))
    await asyncio.sleep(0.01)
    t2 = asyncio.create_task(task("Task-2"))
    
    t1.cancel()
    await asyncio.gather(t1, t2, return_exceptions=True)
    
    # 驗證：Barrier 必須自我恢復健康，接下來的等待不能超時！
    try:
        await asyncio.wait_for(
            asyncio.gather(barrier.wait(), barrier.wait()), 
            timeout=0.2
        )
    except asyncio.TimeoutError:
        pytest.fail("CPython #115031: Barrier is BROKEN after cancellation! State is torn!")
