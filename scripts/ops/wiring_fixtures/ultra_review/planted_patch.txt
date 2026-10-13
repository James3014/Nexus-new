def handler(value: str) -> str:
    return value.strip()


def unsafe() -> object:
    return eval(input())
