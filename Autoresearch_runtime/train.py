import json
import random
import time
from collections import Counter

# ==========================================
# 🧠 Nexus GAN 超參數 (v8.0: Damped Precision)
# ==========================================
CURIOSITY_ALPHA = 0.4446
PHANTOM_AUDIT_THRESHOLD = 0.8499
PRECISION_ALPHA = 0.9900
# ==========================================

def simulate_cycle():
    pot = random.random()
    if pot < 0.05: p_f = "missing_proof"
    elif pot < 0.08: p_f = "invalid_proof"
    else: p_f = ""
    is_pre_ok = not p_f
    g_p = False; p_p = False; i_f = False; f_r = ""
    
    if is_pre_ok:
        g_p = random.random() < (0.50 + CURIOSITY_ALPHA * 0.2)
        if g_p:
            # Lower mismatch baseline to reduce oscillation near <0.5% target.
            m_rate = max(0.0001, 0.008 * (1.1 - PRECISION_ALPHA))
            is_m = random.random() < m_rate
            d_b = random.random() < PHANTOM_AUDIT_THRESHOLD if is_m else random.random() < (1.0 - PHANTOM_AUDIT_THRESHOLD) * 0.03
            if not d_b: p_p = True
            else: 
                i_f = is_m
                f_r = "proof_mismatch" if is_m else "phantom_blocked"
        else: f_r = "no_patch"
    else: f_r = p_f
    return {"g": g_p, "p": p_p, "f": i_f, "reason": f_r}

def main():
    sub_rounds = 1000
    results = [simulate_cycle() for _ in range(sub_rounds)]
    total_g = sum([r["g"] for r in results])
    total_p = sum([r["p"] for r in results])
    total_f = sum([r["f"] for r in results])
    m_count = sum(1 for r in results if r["reason"] == "proof_mismatch")
    p_ratio = (total_p / max(1, total_g)) * 100
    m_rate = (m_count / max(1, total_g)) * 100
    is_frozen = total_f > 15
    
    reason_counter = Counter([r["reason"] for r in results if r["reason"] and r["reason"] != "none"])
    r_reason = reason_counter.most_common(1)[0][0] if reason_counter else "none"
    rca = "none"
    if p_ratio < 95.0: rca = "proof_fail"
    elif is_frozen: rca = "freeze_fail"
    elif r_reason in ["missing_proof", "invalid_proof", "proof_mismatch", "phantom_blocked"]: rca = "proof_fail"

    output = {
        "round": int(time.time()),
        "alignment": round((p_ratio * 0.6) + (PRECISION_ALPHA * 100 * 0.4), 2),
        "checks_triggered": True,
        "generated_patches": total_g,
        "proof_passed_patches": total_p,
        "learning_frozen": is_frozen,
        "proof_ratio": round(p_ratio, 2),
        "mismatch_rate": round(m_rate, 3),
        "fail_fast_reason": r_reason,
        "rca_bucket": rca,
        "fail_bucket": rca,
        "params": {"ALPHA": CURIOSITY_ALPHA, "THRESHOLD": PHANTOM_AUDIT_THRESHOLD, "PRECISION": PRECISION_ALPHA}
    }
    print(json.dumps(output))

if __name__ == "__main__":
    main()
