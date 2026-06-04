from typing import List, Dict, Any
from dataclasses import dataclass
from nexus.governance.domain.blocker_taxonomy import BlockerCode

@dataclass(frozen=True)
class HeatmapMatrix:
    """[Domain] 熱圖渲染矩陣"""
    x_axis_labels: List[str] # 時間桶 (Time Buckets)
    y_axis_labels: List[str] # Blocker Codes
    data_points: List[Dict[str, Any]] # [{"x": str, "y": str, "value": int}]

class HeatmapSeriesBuilder:
    """
    📊 Task: Heatmap Series Builder (Domain)
    職責: 將扁平的觀測事件轉化為二維熱圖矩陣，以凸顯故障群聚 (Clustering)。
    """
    @staticmethod
    def build_matrix(events: List[Dict[str, Any]]) -> HeatmapMatrix:
        """
        events: [{"time": "2026-06-03", "blocker": BlockerCode.DRIFT_DETECTED}]
        """
        matrix_data = {}
        time_buckets = set()
        blocker_codes = set()
        
        for event in events:
            t = event["time"]
            b = event["blocker"]
            time_buckets.add(t)
            blocker_codes.add(b.name)
            
            key = f"{t}|{b.name}"
            matrix_data[key] = matrix_data.get(key, 0) + 1
            
        data_points = []
        for key, value in matrix_data.items():
            t, b = key.split("|")
            data_points.append({"x": t, "y": b, "value": value})
            
        return HeatmapMatrix(
            x_axis_labels=sorted(list(time_buckets)),
            y_axis_labels=sorted(list(blocker_codes)),
            data_points=data_points
        )
