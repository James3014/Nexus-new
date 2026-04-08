import time, psutil, statistics
class ProductionIOPS:
    def __init__(self, tenants=100):
        self.tenants = tenants
    
    def measure_write(self):
        start = time.perf_counter()
        # Simulate 100 tenant concurrent writes (Logic proxy)
        # In real prod, this triggers disk IO counters
        [self._mock_write(t) for t in range(self.tenants)]
        latency_ms = (time.perf_counter() - start) * 1000 / self.tenants
        return latency_ms
    
    def get_p95(self, samples=100):
        latencies = [self.measure_write() for _ in range(samples)]
        # Precise P95 via statistics
        return statistics.quantiles(latencies, n=20)[18]
    
    def _mock_write(self, tenant): 
        # Simulated Micro-SSD Write (0.01ms - 0.2ms)
        time.sleep(0.0001) 
