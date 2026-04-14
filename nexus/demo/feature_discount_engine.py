def calculate_discount(total, is_vip=False, coupon=None):
    discount = 0.0
    if total >= 100:
        discount += 0.10
    if coupon == "SAVE5":
        discount += 0.05
    # BUG: VIP tier not applied yet.
    final = total * (1.0 - discount)
    return round(final, 2)
