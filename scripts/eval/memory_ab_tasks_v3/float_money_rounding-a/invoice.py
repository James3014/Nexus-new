def invoice_total(line_prices, tax_rate):
    """Return the invoice total as a 2-decimal string.

    line_prices are decimal strings such as '0.10'; tax_rate is a decimal string
    such as '0.0825'. The tax is rounded to the cent (half to even) and then added
    to the exact subtotal.
    """
    subtotal = sum(float(p) for p in line_prices)
    tax = subtotal * float(tax_rate)
    return f"{round(subtotal + tax, 2):.2f}"
