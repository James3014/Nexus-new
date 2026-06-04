
import sys
from scripts.governance.check_architecture_fitness import check_dependency_direction, check_module_size

def run_ci_gate():
    print('--- [CI GATE] Architecture Fitness Evaluation ---')
    violations = check_dependency_direction()
    if violations:
        for v in violations: print(f'❌ {v}')
        return False
    print('✅ Fitness Check Passed.')
    return True

if __name__ == "__main__":
    sys.exit(0 if run_ci_gate() else 1)
