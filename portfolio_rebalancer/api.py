import requests
import urllib3

from portfolio_rebalancer.decimal_utils import Decimal, to_decimal

# Disable ssl warning.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Forked from:
# https://github.com/ashpipe/EasyIB/blob/8d07eb6303796313379e7da4c4080b4fa35e5898/src/easyib/easyib.py


class Api:
    """Allows to send REST API requests to Interactive Brokers Client Portal Web API.

    :param url: Gateway session link, defaults to "https://localhost:5000"
    :type url: str, optional
    :param ssl: Usage of SSL certificate, defaults to False
    :type ssl: bool, optional
    """

    def __init__(self, url: str, ssl=False) -> None:
        """Create a new instance to interact with REST API

        :param url: Client Portal URL or HAR logging proxy URL.
        :type url: str, optional
        :param ssl: Usage of SSL certificate, defaults to False
        :type ssl: bool, optional
        """
        self.url = f"{url}/v1/api/"
        self.ssl = ssl
        self._account_id = None
        self.conids = {}
        self.prices = {}
        # Initialize session.
        self.get_accounts()

    def account_id(self) -> str:
        """Returns account ID

        :return: Account ID
        :rtype: str
        """
        if not self._account_id:
            raise ValueError("Account ID not set")

        return self._account_id

    def get_accounts(self) -> list:
        """Returns account info

        :return: list of account info
        :rtype: list
        """
        response = requests.get(f"{self.url}portfolio/accounts", verify=self.ssl)
        response.raise_for_status()

        return response.json()

    def switch_account(self, account_id: str) -> None:
        """Switch selected account to the input account

        :param account_id: account ID of the desired account
        :type account_id: str
        :return: Response from the server
        :rtype: dict
        """
        self._account_id = account_id
        response = requests.post(
            f"{self.url}iserver/account", json={"acctId": account_id}, verify=self.ssl
        )
        if response.ok:
            print(response.json())
        else:
            if response.text == '{"error":"Account already set"}':
                print("Account already set")
            else:
                raise ValueError(
                    f"Error switching account: [{response.status_code}] {response.text}"
                )

    def _get_conid(
        self,
        symbol: str,
        instrument_filters: dict = None,
        contract_filters: dict = {"isUS": True},
    ) -> int:
        """Returns contract id of the given stock instrument

        :param symbol: Symbol of the stock instrument
        :type symbol: str
        :param instrument_filters: Key-value pair of filters to use on the returned instrument data, e.g) {"name": "ISHARES NATIONAL MUNI BOND E", "assetClass": "STK"}
        :type instrument_filters: Dict, optional
        :param contract_filters: Key-value pair of filters to use on the returned contract data, e.g) {"isUS": True, "exchange": "ARCA"}
        :type contract_filters: Dict, optional
        :return: contract id
        :rtype: int
        """
        query = {"symbols": symbol}
        response = requests.get(
            f"{self.url}trsrv/stocks", params=query, verify=self.ssl
        )
        response.raise_for_status()

        dic = response.json()

        if instrument_filters or contract_filters:

            def filter_instrument(instrument: dict) -> bool:
                def apply_filters(x: dict, filters: dict) -> list:
                    positives = list(
                        filter(
                            lambda x: x,
                            [x.get(key) == val for key, val in filters.items()],
                        )
                    )
                    return len(positives) == len(filters)

                if instrument_filters:
                    valid = apply_filters(instrument, instrument_filters)

                    if not valid:
                        return False

                if contract_filters:
                    instrument["contracts"] = list(
                        filter(
                            lambda x: apply_filters(x, contract_filters),
                            instrument["contracts"],
                        )
                    )

                return len(instrument["contracts"]) > 0

            dic[symbol] = list(filter(filter_instrument, dic[symbol]))

        return dic[symbol][0]["contracts"][0]["conid"]

    def get_conid(self, symbol, exchange):
        if symbol in self.conids:
            return self.conids[symbol]

        try:
            conid = self._get_conid(symbol, contract_filters={"exchange": exchange})
            self.conids[symbol] = conid
            return self.conids[symbol]
        except IndexError:
            raise ValueError(f"Unable to find conid for {symbol} on {exchange}")

    def get_portfolio(self) -> dict:
        """Returns portfolio of the selected account with the following keys:
        - conid: Contract ID
        - symbol: Symbol of the stock instrument
        - quantity: Quantity of the stock instrument
        - exchange: Exchange of the stock instrument
        - bid: Bid price
        - ask: Ask price
        - last_price: Last price

        :return: Portfolio
        :rtype: dict
        """
        response = requests.get(
            f"{self.url}portfolio/{self.account_id()}/positions/0", verify=self.ssl
        )
        response.raise_for_status()

        positions = []
        for position in response.json():
            position = {
                "conid": position["conid"],
                "symbol": position["contractDesc"],
                "quantity": to_decimal(position["position"]),
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
        """Returns pricing info of the given position with the following keys:
        - bid: Bid price
        - ask: Ask price
        - last_price: Last price

        :param position: Position to get pricing info for
        :type position: dict
        :param retries: Number of retries to get pricing info, defaults to 10
        :type retries: int, optional

        :return: Pricing info
        :rtype: dict
        """
        if retries <= 0:
            raise ValueError(f"Unable to find bid/ask spread for {position['symbol']}")

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
        response.raise_for_status()

        response = response.json()
        if not response:
            print(f"Retrying {position['symbol']} because response was empty")
            return self.get_pricing_info(position, retries - 1)

        response = response[0]

        required_keys = [last_price, bid, ask]
        key_names = {last_price: "last price", bid: "bid", ask: "ask"}

        missing_or_invalid_keys = [
            key for key in required_keys if key not in response or not response[key]
        ]

        if missing_or_invalid_keys:
            missing_or_invalid_keys_str = ", ".join(
                f"{key} ({key_names[key]})" for key in missing_or_invalid_keys
            )
            print(
                f"Retrying {position['symbol']} because response was incomplete: {response}. Missing or invalid keys: {missing_or_invalid_keys_str}"
            )
            return self.get_pricing_info(position, retries - 1)

        last_price = response[last_price]
        bid = response[bid]
        ask = response[ask]
        print(
            f"Found pricing info for {position['symbol']}: bid={bid}, ask={ask}, last_price={last_price}"
        )
        # Strip out all non-numeric characters. Because I found a ticker that
        # returned `C119.7` instead of `119.7` for this particular field.
        # https://stackoverflow.com/a/1450913/2197402
        last_price = "".join(i for i in last_price if i.isdigit() or i in "-./\\")
        last_price = to_decimal(last_price)
        bid = to_decimal(bid)
        ask = to_decimal(ask)

        self.prices[identifier] = {"last_price": last_price, "bid": bid, "ask": ask}

        return self.prices[identifier]

    def submit_order(self, order: dict, dry_run: bool) -> requests.Response:
        """Submits an order

        :param order: Order to submit
        :type order: dict
        :param dry_run: Whether to actually submit the order
        :type dry_run: bool
        :return: response
        :rtype: requests.Response
        """
        submit_order_url = f"{self.url}iserver/account/{self.account_id()}/orders"
        if dry_run:
            submit_order_url += "/whatif"
        response = requests.post(
            submit_order_url,
            json={"orders": [order]},
            verify=self.ssl,
        )

        return response

    def confirm_order(self, order_id: str) -> requests.Response:
        """Confirms an order

        :param order_id: Order id to confirm
        :type order_id: str
        :return: response
        :rtype: requests.Response
        """
        response = requests.post(
            f"{self.url}iserver/reply/{order_id}",
            json={"confirmed": True},
            verify=self.ssl,
        )

        return response
