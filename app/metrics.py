from collections import defaultdict

metrics: dict[str, int] = defaultdict(int)


def inc(name: str, n: int = 1) -> None:
    metrics[name] += n
