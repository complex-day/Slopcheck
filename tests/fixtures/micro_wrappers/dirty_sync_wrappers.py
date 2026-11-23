def _wrap_int(val: str) -> int:
    """Convert value to int."""
    return int(val)


def _double_val(val: int) -> int:
    res = val * 2
    return res


def run_pipeline(x: str) -> int:
    a = _wrap_int(x)
    b = _double_val(a)
    return b
