def calculate_total_price(items: list[dict]) -> float:
    """
    計算清單中所有項目的總金額。

    此函數修復了原始版本中未處理字串類型輸入的問題（避免字串倍數運算），
    確保所有運算均在數值空間內進行，防止如 '10' * 2 = '1010' 的邏輯錯誤或 TypeError。
    """
    total = 0.0
    for item in items:
        # 強制轉換為數值，修復潛在的字串型態 Bug，並確保運算正確性
        price = float(item.get('price', 0))
        quantity = float(item.get('quantity', 0))
        total += price * quantity
    return total

if __name__ == "__main__":
    # 測試資料：模擬包含數值的購物車項目
    cart = [
        {"name": "Apple", "price": 10, "quantity": 2},
        {"name": "Banana", "price": 5, "quantity": 3}
    ]

    # 預期結果：(10 * 2) + (5 * 3) = 20 + 15 = 35.0
    result = calculate_total_price(cart)
    expected = 35.0

    # 驗證結果並提供清晰的輸出回饋
    if result == expected:
        print(f"✅ 測試通過！計算結果為 {result}，符合預期 {expected}。")
    else:
        error_msg = f"❌ 測試失敗：預期 {expected}，實際得到 {result}"
        print(error_msg)
        raise AssertionError(error_msg)
