#!/usr/bin/env python3
import sys
from pathlib import Path
from nexus.app.learn_scheduler_service import LearnSchedulerService

def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    svc = LearnSchedulerService(repo_root)
    sys.exit(svc.run_scheduler())

if __name__ == "__main__":
    main()
