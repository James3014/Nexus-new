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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    
    plot_optimization_curve(args.csv, args.out)
