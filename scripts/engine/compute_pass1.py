import json
import sys

def compute_scores(jsonl_file):
    results = []
    try:
        with open(jsonl_file, 'r') as f:
            for line in f:
                if not line.strip(): continue
                data = json.loads(line)
                results.append({
                    'task_id': data.get('task_id', 'N/A'),
                    'pass_1': data.get('pass@1', False),
                    'health': data.get('health_score', 0.0),
                    'reason': data.get('reason', 'N/A')
                })
    except FileNotFoundError:
        print(f"Error: {jsonl_file} not found.")
        return 0.0
    
    total = len(results)
    if total == 0:
        print("No results found.")
        return 0.0
        
    pass1 = sum(1 for r in results if r['pass_1'])
    
    print(f"pass@1: {pass1/total*100:.1f}% ({pass1}/{total})")
    print("\nLast 10 tasks:")
    for r in results[-10:]:
        print(f"{r['task_id']},{r['pass_1']},{r['health']:.2f},\"{r['reason']}\"")
    
    return pass1 / total

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compute_pass1.py <results.jsonl>")
    else:
        compute_scores(sys.argv[1])
