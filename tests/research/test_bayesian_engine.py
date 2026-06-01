import pytest
import numpy as np
from nexus.research.bayesian_engine import BayesianResearchOptimizer, SearchDimension

def test_normalization_denormalization():
    """驗證參數正規化與還原的一致性。"""
    dims = [
        SearchDimension("lr", "real", (1e-5, 1e-1)),
        SearchDimension("batch", "integer", (8, 64)),
        SearchDimension("opt", "categorical", ["adam", "sgd"])
    ]
    optimizer = BayesianResearchOptimizer(dims)
    
    # 測試邊界點
    p1 = {"lr": 1e-5, "batch": 8, "opt": "adam"}
    norm_x = optimizer._normalize_x(p1)
    denorm_p = optimizer._denormalize_x(norm_x)
    assert denorm_p["lr"] == pytest.approx(1e-5)
    assert denorm_p["batch"] == 8
    assert denorm_p["opt"] == "adam"

def test_suggest_returns_valid_params():
    """驗證建議的參數符合搜尋空間定義。"""
    dims = [
        SearchDimension("lr", "real", (0.0, 1.0)),
        SearchDimension("batch", "integer", (10, 20)),
        SearchDimension("opt", "categorical", ["A", "B"])
    ]
    optimizer = BayesianResearchOptimizer(dims)
    
    # 未觀測時建議
    p1 = optimizer.suggest()
    assert 0.0 <= p1["lr"] <= 1.0
    assert 10 <= p1["batch"] <= 20
    assert p1["opt"] in ["A", "B"]

def test_convergence_on_simple_function():
    """
    驗證引擎在簡單目標函數上的收斂能力。
    目標: 極大化 f(x) = -(x - 0.5)^2
    """
    dims = [SearchDimension("x", "real", (0.0, 1.0))]
    optimizer = BayesianResearchOptimizer(dims)
    
    def objective(params):
        x = params["x"]
        return - (x - 0.5)**2
        
    for i in range(15):
        suggestion = optimizer.suggest()
        score = objective(suggestion)
        optimizer.observe(suggestion, score)
        
    # 檢查最終建議是否接近 0.5
    best_params = optimizer.suggest(n_candidates=100)
    assert best_params["x"] == pytest.approx(0.5, abs=0.05)
    
    # 檢查收斂判定
    assert optimizer.convergence_check(tolerance=0.05, patience=5)

def test_categorical_optimization():
    """驗證類別參數的優化邏輯。"""
    dims = [SearchDimension("choice", "categorical", ["bad", "good", "best"])]
    optimizer = BayesianResearchOptimizer(dims)
    
    scores = {"bad": 0.1, "good": 0.5, "best": 0.9}
    
    for _ in range(10):
        p = optimizer.suggest()
        optimizer.observe(p, scores[p["choice"]])
        
    # 最終應該傾向於建議 "best"
    final_p = optimizer.suggest()
    assert final_p["choice"] == "best"
