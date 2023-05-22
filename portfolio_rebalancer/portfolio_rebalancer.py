from decimal import Decimal

import easyib
import requests


class PortfolioRebalancer:
    def __init__(
        self,
        account_id,
        allocations,
        dry_run=True,
        url="https://localhost:5000",
        ssl=False,
    ):
        self.api = easyib.REST()
        self.account_id = account_id
        self.allocations = allocations
        self.conids = {}
        self.prices = {}
        self.dry_run = dry_run
        self.url = f"{url}/v1/api/"
        self.ssl = ssl

    def prepared_allocations(self):
        allocations = self.allocations.copy()

        # Cast the percent of each allocation to a Decimal.
        for allocation in allocations:
            allocation["percent"] = self.to_decimal(allocation["percent"])

        # Assert that the sum of allocation percents is 100.
        sum_of_allocations = sum(a["percent"] for a in allocations)
        if not sum_of_allocations == 100:
            raise ValueError(f"Allocations do not sum to 100: {sum_of_allocations}")

        # Fetch the conids for each allocation.
        for allocation in allocations:
            allocation["conid"] = self.get_conid(
                allocation["symbol"], allocation["exchange"]
            )

        # Fetch the bid/ask spreads for each allocation.
        for allocation in allocations:
            allocation |= self.get_pricing_info(allocation)

        return allocations

    # The EasyIB method is too limited, so I'm using the ibkr API directly.
    def get_portfolio(self):
        response = requests.get(
            f"{self.url}portfolio/{self.account_id}/positions/0", verify=self.ssl
        )
        positions = []
        for position in response.json():
            position = {
                "conid": position["conid"],
                "symbol": position["contractDesc"],
                "quantity": self.to_decimal(position["position"]),
                "exchange": position["listingExchange"],
            }
            position |= self.get_pricing_info(position)
            positions.append(position)

        return positions

    # Calls the "Market Data Snapshot (Beta)" endpoint.
    # https://www.interactivebrokers.com/api/doc.html#tag/Market-Data/paths/~1md~1snapshot/get
    def get_pricing_info(
        self, position: dict[str, str], retries=10
    ) -> dict[str, Decimal]:
        identifier = f"{position['conid']}@{position['exchange']}:CS"
        if identifier in self.prices:
            return self.prices[identifier]

        # https://gist.github.com/theloniusmunch/9b14d320fd1c3aca550fc8d54c446ce0
        last_price = "31"
        bid = "84"
        ask = "86"
        params = {"conids": identifier, "fields": f"{last_price},{bid},{ask}"}
        response = requests.get(
            f"{self.url}md/snapshot", params=params, verify=self.ssl
        )
        if not response.ok:
            raise ValueError(
                f"Unable to find bid/ask spread for {position['symbol']} because {response.json()}"
            )

        response = response.json()
        if not response:
            if retries > 0:
                print(f"Retrying {position['symbol']} because response was empty")
                return self.get_pricing_info(position, retries - 1)
            else:
                raise ValueError(
                    f"Unable to find bid/ask spread for {position['symbol']}"
                )

        response = response[0]

        if last_price not in response or bid not in response or ask not in response:
            if retries > 0:
                print(
                    f"Retrying {position['symbol']} because response was incomplete: {response}"
                )
                return self.get_pricing_info(position, retries - 1)
            else:
                raise ValueError(
                    f"Unable to find bid/ask spread for {position['symbol']}"
                )

        last_price = response[last_price]
        bid = response[bid]
        ask = response[ask]
        # Strip out all non-numeric characters. Because I found a ticker that
        # returned `C119.7` instead of `119.7` for this particular field.
        # https://stackoverflow.com/a/1450913/2197402
        last_price = ''.join(i for i in last_price if i.isdigit() or i in '-./\\')
        last_price = self.to_decimal(last_price)
        bid = self.to_decimal(bid)
        ask = self.to_decimal(ask)
        print(f"Found pricing info for {position['symbol']}: bid={bid}, ask={ask}, last_price={last_price}")

        self.prices[identifier] = {"last_price": last_price, "bid": bid, "ask": ask}

        return self.prices[identifier]

    def to_decimal(self, number):
        return Decimal(str(number))

    # Truncates a number to two decimal places in addition to casting it to a Decimal.
    def to_truncated_decimal(self, number):
        return int(Decimal(str(number)) * 100) / Decimal(100)

    def get_conid(self, symbol, exchange):
        if symbol in self.conids:
            return self.conids[symbol]

        try:
            conid = self.api.get_conid(symbol, contract_filters={"exchange": exchange})
            self.conids[symbol] = conid
            return self.conids[symbol]
        except IndexError:
            raise ValueError(f"Unable to find conid for {symbol} on {exchange}")

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

    # def submit_orders(self, order_messages: list[dict[str, any]]) -> None:
    #     response = requests.post(f"{self.url}iserver/account/{self.account_id}/orders", json={"orders": order_messages}, verify=self.ssl)
    #     import pdb; pdb.set_trace()
    #     return response

    def run(self):
        self.api.get_accounts()
        self.api.switch_account(self.account_id)

        net_value = self.to_decimal(self.api.get_netvalue())
        print(f"Net portfolio value: {net_value}")

        portfolio = self.get_portfolio()
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
            current_percent = self.to_truncated_decimal(current_value / net_value * 100)
            target_percent = allocation["percent"]
            print(
                f"{symbol}: Current Percent = {current_percent}%, Target Percent = {target_percent}%"
            )

            target_quantity = net_value * target_percent / 100 / last_price
            quantity_different = self.to_truncated_decimal(
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

        submit_order_url = f"{self.url}iserver/account/{self.account_id}/orders"
        if self.dry_run:
            print('Dry run mode, executing "whatif" trades instead of real trades.')
            submit_order_url += "/whatif"
        else:
            print("Executing real trades now!")

        responses = []
        orders = sell_trades + buy_trades
        for order in orders:
            response = requests.post(
                f"{self.url}iserver/account/{self.account_id}/orders",
                json={"orders": [order]},
                verify=self.ssl,
            )
            if response.ok:
                print(
                    f"Successfully submitted order: {self.prettify_order_message(order)}"
                )
                for response in response.json():
                    print(response)
                    responses.append(response)
            else:
                import pdb

                pdb.set_trace()
                raise ValueError(
                    f"Failed to submit order: {self.prettify_order_message(order)} {response.text}"
                )

        user_input = input("Confirm all trades (yes/no): ")
        if user_input.lower() == "yes":
            for response in responses:
                self.api.reply_yes(response["id"])
        else:
            print("Aborting trades.")
