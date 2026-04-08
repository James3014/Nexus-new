#!/bin/bash
echo "===================================================="
echo "🛡️  Nexus Singularity OS v23 - NAS Hardened Dashboard"
echo "===================================================="
if [ -f "evolution_traces.jsonl" ]; then
    echo -e "\n🧬  [NEURAL ARCHITECTURE SEARCH]"
    echo "---------------------------------------------------------"
    gen=$(tail -n 1 evolution_traces.jsonl | jq -r '.gen')
    fit=$(tail -n 1 evolution_traces.jsonl | jq -r '.fitness')
    echo "Current Generation: Gen $gen"
    echo "Max Fitness Score: $fit (Optimized)"
    echo "---------------------------------------------------------"
fi
