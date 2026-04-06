import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import argparse

def plot_optimization_curve(csv_path: str, output_image: str):
    """
    📉 繪製 Nexus AutoResearch 進化曲線 (Optimized v3)。
    """
    path = Path(csv_path)
    if not path.exists():
        print(f"❌ [Error] {csv_path} not found.")
        return

    df = pd.read_csv(csv_path)
    
    # 映射 status 到 committed (IMPROVED -> 1, ROLLBACK -> 0)
    if 'status' in df.columns:
        df['committed'] = df['status'].apply(lambda x: 1 if x == 'IMPROVED' else 0)
    else:
        df['committed'] = 0

    plt.figure(figsize=(10, 6))
    plt.plot(df['round'], df['score'], 'b-', label='FlashJudge Score', linewidth=2)
    
    # 標註 Commit 點 (綠色)
    commits = df[df['committed'] == 1]
    plt.scatter(commits['round'], commits['score'], c='green', s=100, label='Successful Commit', zorder=5)
    
    # 標註 Rollback 點 (淡灰色)
    rollbacks = df[df['committed'] == 0]
    plt.scatter(rollbacks['round'], rollbacks['score'], c='gray', s=40, alpha=0.5, label='Rollback', zorder=4)

    plt.title(f'Nexus AutoResearch Evolution: {path.stem.replace("optimization_curve_", "")}', fontsize=14, pad=20)
    plt.xlabel('Iteration Rounds', fontsize=12)
    plt.ylabel('FlashJudge / Utility Score', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend()
    
    plt.tight_layout()
    plt.savefig(output_image, dpi=300)
    print(f"✅ [Viz] High-res curve crystallized at {output_image}")

def plot_wisdom_curve(output_image: str):
    """
    🧠 繪製 Nexus Wisdom 演化曲線 (v23 Burn-in)。
    """
    metrics_path = Path(".nexus/metrics/feedback_events.jsonl")
    if not metrics_path.exists():
        print("❌ [Error] No wisdom metrics found.")
        return

    data = []
    import json
    with open(metrics_path, "r") as f:
        for line in f:
            data.append(json.loads(line))
    
    df = pd.DataFrame(data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')
    df = df.sort_values('timestamp')
    df['event_count'] = range(1, len(df) + 1)
    
    fig, ax1 = plt.subplots(figsize=(12, 7))
    
    # 軸 1: 累積事件數
    ax1.plot(df['timestamp'], df['event_count'], 'g-', label='Cumulative Events', linewidth=2)
    ax1.set_xlabel('Time')
    ax1.set_ylabel('Events Count', color='g')
    ax1.tick_params(axis='y', labelcolor='g')
    
    # 軸 2: 信心度演進 (Confidence)
    if 'confidence' in df.columns:
        ax2 = ax1.twinx()
        ax2.plot(df['timestamp'], df['confidence'], 'b--', label='Wisdom Confidence', alpha=0.6)
        ax2.set_ylabel('Confidence (0-1)', color='b')
        ax2.tick_params(axis='y', labelcolor='b')
        ax2.axhline(y=0.8, color='r', linestyle=':', label='Target Confidence (0.8)')

    plt.title('Nexus v23 Wisdom Burn-in Evolution')
    fig.tight_layout()
    plt.savefig(output_image, dpi=300)
    print(f"📊 [Viz] Wisdom evolution curve crystallized at {output_image}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="Standard optimization CSV")
    parser.add_argument("--out", default="evolution.png")
    parser.add_argument("--kpi", choices=["optimization", "wisdom"], default="optimization")
    args = parser.parse_args()
    
    if args.kpi == "wisdom":
        plot_wisdom_curve(args.out)
    else:
        if not args.csv:
            print("❌ --csv is required for optimization KPI")
        else:
            plot_optimization_curve(args.csv, args.out)
