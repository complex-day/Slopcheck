def reusable_helper(x: int) -> int:
    return x + 1


def multi_statement_func(a: int, b: int) -> int:
    step1 = a * 2
    step2 = b * 3
    result = step1 + step2
    return result


def caller():
    val1 = reusable_helper(10)
    val2 = reusable_helper(20)
    res = multi_statement_func(val1, val2)
    return res
