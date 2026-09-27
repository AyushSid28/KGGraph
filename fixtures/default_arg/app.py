def helper():
    return 1


def f(x=helper()):
    return x
