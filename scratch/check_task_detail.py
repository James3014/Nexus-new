import datasets

print("📦 Loading princeton-nlp/SWE-bench_Verified...")
dataset = datasets.load_dataset("princeton-nlp/SWE-bench_Verified", split="test")

target_ids = ["astropy__astropy-13033", "astropy__astropy-14096", "astropy__astropy-14365"]

for t_id in target_ids:
    instance = next((row for row in dataset if row["instance_id"] == t_id), None)
    if instance:
        print(f"\n==========================================")
        print(f"Task ID: {instance['instance_id']}")
        print(f"Problem Statement:\n{instance['problem_statement'][:1000]}")
        if len(instance['problem_statement']) > 1000:
            print("...[truncated]...")
    else:
        print(f"\n❌ Task {t_id} not found in dataset")
