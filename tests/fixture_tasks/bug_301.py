# Scenario: Bug fix in data processing
def process_data(data):
    # Intentional bug: division by zero
    return [x / 0 for x in data]
