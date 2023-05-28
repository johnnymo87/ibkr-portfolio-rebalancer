from decimal import Decimal


def to_decimal(number):
    return Decimal(str(number))


# Truncates a number to two decimal places in addition to casting it to a Decimal.
def to_truncated_decimal(number):
    return int(Decimal(str(number)) * 100) / Decimal(100)
