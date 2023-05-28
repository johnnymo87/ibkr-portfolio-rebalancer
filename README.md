# Portfolio Rebalancer

Portfolio Rebalancer is a Python application that helps you rebalance your investment portfolio using the Interactive Brokers Client Portal API. It calculates the necessary buy and sell orders to adjust your portfolio to the desired asset allocation percentages.

The application is designed for my specific use-case, and may not be well-fit to your needs. But I've open-sourced it just to help the commuity document how to do such things. Also, to that effect, please check out [ashpipe/EasyIB](https://github.com/ashpipe/EasyIB), which this project is inspired by.

**Note**: This application is for demonstration purposes only and should be thoroughly tested and modified according to your needs before using it for real transactions.

## Features

* Fetch current portfolio positions.
* Calculate buy and sell orders to achieve desired asset allocation.
* Display rebalance orders.
* Execute rebalance orders.

## API Targetted
This application talks to the Interactive Brokers Client Portal API. For more, see [their documentation](https://www.interactivebrokers.com/api/doc.html) of it.

## Authenication
This application assumes a gateway session is active and authenticated. Read https://interactivebrokers.github.io/cpwebapi/ for context. This application relies on a dockerized version of the authentication gateway spoken about in that document: [Voyz/IBeam](https://github.com/voyz/ibeam).

## Setup

1. Install or update `pyenv` (and `python-build` to get access to recent releases of python).
   ```
   brew update && brew install python-build pyenv
   brew update && brew upgrade python-build pyenv
   ```
1. Install python.
   ```
   pyenv install $(cat ./.python-version)
   ```
1. Install poetry.
   ```
   curl -sSL https://install.python-poetry.org | python -
   ```
1. Copy `config.yaml.sample` to `config.yaml`.
   ```
   cp config.yaml.sample config.yaml
   ```
1. Fill out the `.config.yaml` with your Interactive Broker account id(s) and desired allocations.
1. Copy `credentials.list.sample` to `credentials.list`.
   ```
   cp credentials.list.sample credentials.list
   ```
1. Fill out the `credentials.list` with your Interactive Broker username and password.

## Run

* Turn on the authentication gateway:
  ```
  docker-compose up -d && docker-compose logs -f
  ```
* Respond to the 2FA login verification request on your phone. Once you do this, you should see in the logs of the gateway that you're authenticated. To double check, you can run the following command:
  ```
  curl -X GET "https://localhost:5000/v1/api/one/user" -k
  ```
* Dry-run the app (will print to STDOUT):
  ```
  poetry run python -m portfolio_rebalancer
  ```
* Really run the app (will execute real trades):
  ```
  poetry run python -m portfolio_rebalancer --execute
  ```
* Run the auto formatter:
  ```
  poetry run pre-commit run --all-files
  ```

## Add a new python package
This app makes use of [`poetry`](https://python-poetry.org/) to manage packages. See docs there for how to add packages.

## Contributing

If you'd like to contribute to the project, please feel free to submit a pull request or open an issue to discuss your ideas.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.
