
def get_canary_gate(risk_tier):
    return 0.01 if risk_tier.name == 'P0_ULTRA' else 0.1
