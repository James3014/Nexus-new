import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
from scipy.stats import norm

@dataclass
class SearchDimension:
    name: str
    dim_type: str           # "real" | "integer" | "categorical"
    bounds: Union[Tuple[float, float], List[Any]]
    prior: str = "uniform"

class ResearchSearchSpace:
    """
    🧬 DeepScientist Search Space
    用於定義研究參數的範圍與類型。
    """
    def __init__(self):
        self.dimensions: List[SearchDimension] = []

    def add_dimension(self, name: str, low: float, high: float, dim_type: str = "real") -> None:
        self.dimensions.append(SearchDimension(name=name, dim_type=dim_type, bounds=(low, high)))
        
    def add_categorical(self, name: str, options: List[Any]) -> None:
        self.dimensions.append(SearchDimension(name=name, dim_type="categorical", bounds=options))

class BayesianResearchOptimizer:
    """
    🧠 Bayesian Optimization Engine (Pure Python/Numpy Implementation)
    基於高斯過程 (GP) 的輕量級超參優化器，具有數值穩定性與 O(N^2) 預測效能優化。
    """
    def __init__(self, space: Union[ResearchSearchSpace, List[SearchDimension]], noise: float = 1e-6):
        if isinstance(space, ResearchSearchSpace):
            self.dimensions = space.dimensions
        else:
            self.dimensions = space
        self.noise = noise
        self.X_observed: List[np.ndarray] = []
        self.y_observed: List[float] = []
        self.length_scale = 1.0
        
    def _normalize_x(self, params: Dict[str, Any]) -> np.ndarray:
        """將字典參數正規化為 [0, 1] 向量。"""
        x = np.zeros(len(self.dimensions))
        for i, dim in enumerate(self.dimensions):
            val = params[dim.name]
            if dim.dim_type in ("real", "integer"):
                low, high = dim.bounds
                diff = high - low
                x[i] = (val - low) / diff if diff > 0 else 0.5
            elif dim.dim_type == "categorical":
                idx = dim.bounds.index(val) if val in dim.bounds else 0
                x[i] = idx / (len(dim.bounds) - 1) if len(dim.bounds) > 1 else 0.5
        return x

    def _denormalize_x(self, x_norm: np.ndarray) -> Dict[str, Any]:
        """從 [0, 1] 向量還原為原始參數。"""
        params = {}
        for i, dim in enumerate(self.dimensions):
            val = x_norm[i]
            if dim.dim_type == "real":
                low, high = dim.bounds
                params[dim.name] = float(low + val * (high - low))
            elif dim.dim_type == "integer":
                low, high = dim.bounds
                params[dim.name] = int(round(low + val * (high - low)))
            elif dim.dim_type == "categorical":
                idx = int(round(val * (len(dim.bounds) - 1)))
                idx = max(0, min(idx, len(dim.bounds) - 1))
                params[dim.name] = dim.bounds[idx]
        return params

    def _kernel(self, X1: np.ndarray, X2: np.ndarray) -> np.ndarray:
        """RBF Kernel with numerical stability."""
        sqdist = np.sum(X1**2, 1).reshape(-1, 1) + np.sum(X2**2, 1) - 2 * np.dot(X1, X2.T)
        sqdist = np.maximum(sqdist, 0.0)  # Avoid negative distances due to float errors
        return np.exp(-0.5 / self.length_scale**2 * sqdist)

    def observe(self, params: Dict[str, Any], score: float) -> None:
        """記錄一個觀測點 (參數與得分)。"""
        self.X_observed.append(self._normalize_x(params))
        self.y_observed.append(score)

    def predict(self, X_s: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """給定候選點 X_s，預測均值與標準差。"""
        if not self.X_observed:
            return np.zeros(X_s.shape[0]), np.ones(X_s.shape[0])
        
        X = np.array(self.X_observed)
        y = np.array(self.y_observed).reshape(-1, 1)
        
        K = self._kernel(X, X)
        K[np.diag_indices_from(K)] += self.noise
        
        try:
            L = np.linalg.cholesky(K)
        except np.linalg.LinAlgError:
            # Jitter fallback for non-positive definite kernels
            K[np.diag_indices_from(K)] += 1e-4
            L = np.linalg.cholesky(K)
            
        K_s = self._kernel(X, X_s)
        Lk = np.linalg.solve(L, K_s)
        mu = np.dot(Lk.T, np.linalg.solve(L, y)).reshape(-1)
        
        # Calculate variance efficiently: diag of RBF kernel is 1, avoiding O(N^2) memory/compute
        s2 = np.ones(X_s.shape[0]) - np.sum(Lk**2, axis=0)
        return mu, np.sqrt(np.maximum(s2, 1e-9))

    def suggest(self, n_candidates: int = 1000) -> Dict[str, Any]:
        """使用預期改善 (EI) 獲取函數推薦下一個實驗點。"""
        if not self.X_observed:
            # 第一輪: 隨機採樣
            random_x = np.random.uniform(0, 1, len(self.dimensions))
            return self._denormalize_x(random_x)
        
        # 1. 隨機採樣大量候選點
        X_candidates = np.random.uniform(0, 1, (n_candidates, len(self.dimensions)))
        
        # 2. 預測候選點的分數
        mu, sigma = self.predict(X_candidates)
        
        # 3. 計算 EI (Expected Improvement)
        y_max = np.max(self.y_observed)
        improvement = mu - y_max
        
        with np.errstate(divide='ignore', invalid='ignore'):
            Z = improvement / sigma
            ei = np.where(sigma > 1e-9, improvement * norm.cdf(Z) + sigma * norm.pdf(Z), 0.0)
            
        # 4. 取得 EI 最大點
        best_idx = np.argmax(ei)
        return self._denormalize_x(X_candidates[best_idx])

    def convergence_check(self, tolerance: float = 0.01, patience: int = 5) -> bool:
        """判定是否收斂。"""
        if len(self.y_observed) < patience:
            return False
        
        recent_scores = self.y_observed[-patience:]
        return (max(recent_scores) - min(recent_scores)) < tolerance
