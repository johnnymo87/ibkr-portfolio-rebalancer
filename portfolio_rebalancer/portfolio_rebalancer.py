from decimal import Decimal

from portfolio_rebalancer.decimal_utils import to_decimal, to_truncated_decimal


class PortfolioRebalancer:
    def __init__(self, account_id, allocations, api, dry_run=True):
        self.account_id = account_id
        self.allocations = allocations
        self.api = api
        self.dry_run = dry_run

    def prepared_allocations(self) -> list[dict[str, any]]:
        """Prepare the allocations for rebalancing by fetching the conids and
        pricing info for each allocation. Each dictionary has the following
        keys:
        - symbol: Ticker symbol
        - exchange: Exchange where the position is listed
        - percent: Percent of the portfolio to allocate to this position
        - conid: Contract ID
        - bid: Bid price
        - ask: Ask price
        - last_price: Last price

        :return: Prepared allocations
        :rtype: list[dict[str, any]]
        """
        allocations = self.allocations.copy()

        # Cast the percent of each allocation to a Decimal.
        for allocation in allocations:
            allocation["percent"] = to_decimal(allocation["percent"])

        # Assert that the sum of allocation percents is 100.
        sum_of_allocations = sum(abs(a["percent"]) for a in allocations)
        if not sum_of_allocations == 100:
            raise ValueError(f"Allocations do not sum to 100: {sum_of_allocations}")

        # Fetch the conids for each allocation.
        for allocation in allocations:
            allocation["conid"] = self.api.get_conid(
                allocation["symbol"], allocation["exchange"]
            )

        # Fetch the bid/ask spreads for each allocation.
        for allocation in allocations:
            allocation |= self.api.get_pricing_info(allocation)

        return allocations

    # TODO: Figure out how to give the `quantity` arument a `decimal` type.
    def to_order_message(
        self, side: str, position: dict[str, any], quantity
    ) -> dict[str, any]:
        if side not in ["BUY", "SELL"]:
            raise ValueError(f"Invalid side: {side}, must be BUY or SELL")

        price = position["bid"] if side == "BUY" else position["ask"]

        return {
            "side": side,
            "conid": position["conid"],
            "ticker": position["symbol"],
            "price": float(str(price)),
            "quantity": float(str(quantity)),
            "orderType": "LMT",
            "tif": "DAY",
            # As a safety measure, reject orders if we're outside of regular
            # trading hours.
            "outsideRth": False,
            # As a safety measure, reject orders for a size or price determined
            # to be potentially erroneous or out of line with an orderly
            # market.
            "useAdaptive": True,
        }

    def prettify_order_message(self, o: dict[str, str]) -> str:
        return f"{o['side']} {o['quantity']} of {o['ticker']} @ {o['price']}"

    def run(self):
        self.api.switch_account(self.account_id)

        net_value = self.api.get_netvalue()
        print(f"Net portfolio value: {net_value}")

        portfolio = self.api.get_portfolio()
        print(f"Current portfolio: {portfolio}")

        allocations = self.prepared_allocations()

        sell_trades = []
        buy_trades = []

        # portfolio_symbols = {p["symbol"] for p in portfolio}
        # allocation_symbols = {a["symbol"] for a in self.allocations}
        # prices = self.get_prices(portfolio_symbols | allocation_symbols)

        # Calculate the rebalancing trades

        # First, sell all positions that are not in the target allocations.
        allocation_symbols = {a["symbol"] for a in allocations}
        for p in portfolio:
            if p["symbol"] not in allocation_symbols:
                message = self.to_order_message("SELL", p, p["quantity"])
                sell_trades.append(message)

        # Next, calculate the target allocation for each symbol.
        for allocation in allocations:
            symbol = allocation["symbol"]
            print(f"Processing symbol: {symbol}")

            last_price = allocation["last_price"]
            print(f"{symbol}: Last Price = {last_price}")

            current_quantity = next(
                (p["quantity"] for p in portfolio if p["symbol"] == symbol), Decimal(0)
            )
            current_value = last_price * current_quantity
            # Truncate current percent to 2 decimal places.
            current_percent = to_truncated_decimal(current_value / net_value * 100)
            target_percent = allocation["percent"]
            print(
                f"{symbol}: Current Percent = {current_percent}%, Target Percent = {target_percent}%"
            )

            target_quantity = net_value * target_percent / 100 / last_price
            quantity_different = to_truncated_decimal(
                abs(target_quantity - current_quantity)
            )
            print(f"{symbol}: Current Quantity = {current_quantity}")

            if current_quantity > target_quantity:
                print(f"{symbol}: Must sell {quantity_different} shares.")
                message = self.to_order_message("SELL", allocation, quantity_different)
                sell_trades.append(message)
            elif current_quantity < target_quantity:
                print(f"{symbol}: Must buy {quantity_different} shares.")
                message = self.to_order_message("BUY", allocation, quantity_different)
                buy_trades.append(message)
            else:
                print(f"{symbol}: No trades necessary.")

        # Execute the rebalancing trades.

        print("Sell trades:")
        for sell_trade in sell_trades:
            print(self.prettify_order_message(sell_trade))
        print("Buy trades:")
        for buy_trade in buy_trades:
            print(self.prettify_order_message(buy_trade))

        if self.dry_run:
            print('Dry run mode, executing "whatif" trades instead of real trades.')
        else:
            print("Executing real trades now!")

        order_responses = []
        orders = sell_trades + buy_trades
        for order in orders:
            order_response = self.api.submit_order(order, self.dry_run)
            if order_response.ok:
                print(
                    f"Successfully submitted order: {self.prettify_order_message(order)}"
                )
                print(order_response.json())
                order_responses.append(order_response.json())
            else:
                status_code = order_response.status_code
                error_text = order_response.text
                raise ValueError(
                    f"Failed to confirm order: {self.prettify_order_message(order)} status_code={status_code}, error_text={error_text}"
                )

        user_input = input("Confirm all trades (yes/no): ")
        if user_input.lower() == "yes":
            for order_response, order in zip(order_responses, orders):
                order_message_id = order_response[0]["id"]
                confirm_response = self.api.confirm_order(order_message_id)
                if confirm_response.ok:
                    print(
                        f"Successfully confirmed order: {self.prettify_order_message(order)}"
                    )
                    print(confirm_response.json())
                else:
                    status_code = confirm_response.status_code
                    error_text = confirm_response.text
                    raise ValueError(
                        f"Failed to confirm order: {self.prettify_order_message(order)} status_code={status_code}, error_text={error_text}"
                    )

        else:
            print("Aborting trades.")
