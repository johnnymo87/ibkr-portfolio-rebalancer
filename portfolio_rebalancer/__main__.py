import sys

import yaml

from portfolio_rebalancer.api import Api
from portfolio_rebalancer.portfolio_rebalancer import PortfolioRebalancer

# Load config from a separate YAML file.
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


# Check if the --execute flag is passed.
execute = "--execute" in sys.argv
# If --execute is not passed, then we are in dry-run mode.
dry_run = not execute

har_log = "--har-log" in sys.argv
if har_log:
    url = config["har_logging_proxy_url"]
else:
    url = config["client_portal_url"]

for accounts in config["accounts"]:
    account_id = accounts["account_id"]
    print(f"Rebalancing account: {accounts['name']}")
    portfolio_cap = PortfolioCap(accounts.get("portfolio_cap"))
    print(f"Portfolio Cap: {portfolio_cap}")
    allocations = accounts["allocations"]
    print(f"Target allocations: {allocations}")
    api = Api(url=url)
    portfolio_rebalancer = PortfolioRebalancer(
        account_id=account_id, allocations=allocations, api=api, dry_run=dry_run
    )
    portfolio_rebalancer.run()
