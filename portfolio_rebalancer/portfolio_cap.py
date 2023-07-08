class PortfolioCap:
    """A portfolio cap is the maximum amount of cash that can be invested in a
    portfolio. This is useful for testing out changes with less than the full
    value of the portfolio.

    There are three kinds of caps: no cap, a percentage cap, and a dollar cap.
    If the `portfolio_cap` argument is `None`, then there is no cap. If the
    `portfolio_cap` argument is a string, and it starts with "$", then it is a
    dollar cap. If the `portfolio_cap` argument is a string, and it ends with
    "%", then it is a percentage cap.
    """
    def __init__(self, portfolio_cap: str|None):
        if portfolio_cap is None:
            self.portfolio_cap = None
            self.kind = "unlimited"
        if self.portfolio_cap.startswith("$"):
            self.portfolio_cap = Decimal(portfolio_cap[1:])
            self.kind = "dollars"
        elif self.portfolio_cap.endswith("%"):
            self.portfolio_cap = Decimal(portfolio_cap[:-1])
            self.kind = "percent"
        else:
            raise ValueError(
                "portfolio_cap must be prefixed with '$' or suffixed with '%'"
            )

    def __repr__(self):
        if self.kind == "unlimited":
            return f"PortfolioCap({self.kind!r})"
        else:
            return f"PortfolioCap({self.portfolio_cap!r} {self.kind!r})"

    def apply_cap(self, portfolio_value: Decimal) -> Decimal:
        """Takes a portfolio value and returns it with the cap applied.

        :param portfolio_value: Portfolio value
        :type portfolio_value: Decimal
        :return: Cap
        :rtype: Decimal
        """
        if self.kind == "unlimited":
            return portfolio_value
        elif self.kind == "dollar":
            return max(self.portfolio_cap, portfolio_value)
        elif self.kind == "percent":
            return portfolio_value * self.portfolio_cap / 100
        else:
            raise ValueError(f"Invalid kind: {self.kind}")
