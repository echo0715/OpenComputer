# Simple calculator module with several bugs to fix.


def add(a, b):
    return a + b


def substract(a, b):
    # Bug: function name is misspelled ("substract" should be "subtract")
    return a - b


def multiply(a, b):
    # Bug: uses addition instead of multiplication
    return a + b


def divide(a, b):
    # Bug: no return statement
    result = a / b


if __name__ == "__main__":
    print(add(2, 3))
    print(multiply(4, 5))
