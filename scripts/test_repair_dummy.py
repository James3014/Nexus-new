def calculate_total_price(items: list[dict]):
    total = 0
    for item in items:
        # 這裡有一個故意的 Bug：把單價當成了字串串接，而不是相乘後加上去
        total += item['price'] * item['quantity']
    return total

if __name__ == "__main__":
    cart = [
        {"name": "Apple", "price": 10, "quantity": 2},
        {"name": "Banana", "price": 5, "quantity": 3}
    ]
    # 預期：(10*2) + (5*3) = 20 + 15 = 35
    result = calculate_total_price(cart)
    assert result == 35, f"Expected 35, got {result}"
    print("Test passed!")
