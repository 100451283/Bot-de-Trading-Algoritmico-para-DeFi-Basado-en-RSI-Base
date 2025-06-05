import requests
import time
import json
from datetime import datetime
from uniswapTrader import UniswapTrader
from zoneinfo import ZoneInfo

class AdvancedTradingBot:
    trader_coins = {
        "usdc": "USDC_BASE",
        "ethereum": "WETH_BASE",
        "degen-base": "DEGEN",
        "aerodrome-finance": "AERO"
    }
    def __init__(
        self,
        coin_id,
        profit_take,       # e.g., 10 means +$10 net profit => sell all
        profit_stop,       # e.g., -10 means -$10 net loss => sell all,
        initial_balance_usdc,
        wallet_address,
        private_key=None
    ):
        self.coin_id = coin_id

        try:
         self.trader_coin = self.trader_coins[coin_id]
        except KeyError:
            pass
        
        self.profit_take = profit_take  # Sell all if net_profit >= this
        self.profit_stop = profit_stop  # Sell all if net_profit <= this
        
        self.check_interval = 3600 # CHANGE (seconds -> 1 hours)

        self.wallet_address = wallet_address
        self.private_key = private_key

        self.trader = UniswapTrader(
            wallet_address=wallet_address,
            private_key=private_key,
        ) if private_key else None
                
        # Balances
        self.usdc_balance = initial_balance_usdc
        self.coin_balance = 0
        self.holding = False
        
        # Price baseline 
        self.baseline_price = None
        
        self.cg_api_url = f"https://api.coingecko.com/api/v3/coins/{self.coin_id}"
        
        self.running = True

        # RSI settings
        self.rsi_period = 14 # CHANGE (period for RSI calculation -> 14)
        self.price_history = []  # store recent prices for RSI

        # Track initial capital for net profit
        self.initial_capital = initial_balance_usdc
        
    def terminate(self):
        """Terminate the bot loop."""
        self.running = False

    def get_advanced_price_data(self):
        try:
            response = requests.get(
                self.cg_api_url,
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false"
                }
            )
            response.raise_for_status()
            data = response.json()
            current_price = data["market_data"]["current_price"]["usd"]
            volume_24h = data["market_data"]["total_volume"]["usd"]
            return {
                "current_price": current_price,
                "volume_24h": volume_24h
            }
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None

    def compute_rsi(self, prices):
        """
        Compute RSI for the list of prices using the standard formula:
            RSI = 100 - (100 / (1 + RS))
        where
            RS = avg_gain / avg_loss
        """
        if len(prices) < 2:
            return None  # Not enough data

        gains, losses = [], []
        for i in range(1, len(prices)):
            diff = prices[i] - prices[i-1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(diff))

        avg_gain = sum(gains) / len(gains) if len(gains) else 0
        avg_loss = sum(losses) / len(losses) if len(losses) else 0

        if avg_loss == 0:
            # No losses => RSI = 100
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def log_trade(self, action, amount, price):
        """Log a trade action to trades.json file."""
        trade = {
            "timestamp": time.time(),
            "wallet": self.wallet_address,
            "action": action,
            "coin": self.coin_id,
            "amount": round(float(amount), 6),
            "price": round(float(price), 2)
        }
        with open("trades.json", "a") as f:
            f.write(json.dumps(trade) + "\n")
    
    def clear_trade_log(self):
        """Clear the contents of trades.json file."""
        with open("trades.json", "w") as f:
            f.write("")

    def get_portfolio_value(self, current_price):
        """Total USD value of USDC + token holdings."""
        return float(self.usdc_balance) + (float(self.coin_balance) * float(current_price))

    def run(self):
        count = 0
        print(f"Starting advanced trading bot for {self.coin_id} on wallet {self.wallet_address}...")
        
        print("----------------------------------------------------------\n")

        self.clear_trade_log()

        while self.running:
            print("----------------------------------------------------------")
            print("Iteration:", count)
            count += 1
            
            data = self.get_advanced_price_data()
            if data is None:
                print("Skipping this interval due to API error.")
                time.sleep(self.check_interval)
                continue

            current_price = data["current_price"]
            volume_24h = 999999999  # Always high, like in simulation
            print(f"\n⏱️ Time: {datetime.now(ZoneInfo('Europe/Madrid')).strftime('%Y-%m-%d %H:%M:%S')} Europe/Madrid")
            print(f"Current price: ${current_price:.2f}")

            # Update RSI price history
            self.price_history.append(current_price)
            if len(self.price_history) > (self.rsi_period + 1):
                self.price_history.pop(0)

            if self.baseline_price is None:
                self.baseline_price = current_price
                print(f"Baseline price set to: ${self.baseline_price:.2f}")

            portfolio_value = self.get_portfolio_value(current_price)
            net_profit = portfolio_value - self.initial_capital
            print(f"Portfolio Value: ${portfolio_value:.2f} | Net Profit: ${net_profit:.2f}")

            # RSI calculation
            rsi = None
            if len(self.price_history) >= self.rsi_period:
                rsi = self.compute_rsi(self.price_history[-self.rsi_period:])
                if rsi is not None:
                    print(f"RSI ({self.rsi_period}-period): {rsi:.2f}")
            else:
                needed = self.rsi_period - len(self.price_history)
                print(f"RSI: waiting for {needed} more prices...")

            # === Step 1: Check forced profit take / stop loss ===
            if self.coin_balance > 0:
                if net_profit >= self.profit_take:
                    print(f"Net profit >= {self.profit_take:.2f} => SELL ALL")

                    if self.trader:
                        print(f"Net profit >= {self.profit_take:.2f} => SELL ALL")
                        self.trader.trade(self.trader_coin, "USDC_BASE", self.coin_balance, slippage=1)
                        usdc_gained = self.coin_balance * current_price
                        self.usdc_balance += usdc_gained
                        self.log_trade("FULL_SELL_PROFIT", self.coin_balance, current_price)
                        self.coin_balance = 0
                        break

                elif net_profit <= self.profit_stop:

                    if self.trader:
                        print(f"Net profit <= {self.profit_stop:.2f} => SELL ALL")
                        self.trader.trade(self.trader_coin, "USDC_BASE", self.coin_balance, slippage=1)

                        usdc_gained = self.coin_balance * current_price
                        self.usdc_balance += usdc_gained
                        self.log_trade("FULL_SELL_STOPLOSS", self.coin_balance, current_price)
                        self.coin_balance = 0
                        break

            # === Step 2: RSI-based partial buy/sell ===
            rsi_buy_threshold = 30
            rsi_sell_threshold = 70
            min_trade_value = 1 # CHANGE (in USDC -> 1)

            if volume_24h < 1_000_000:
                print("Volume too low, skipping RSI trades.")
            else:
                # Buy
                if rsi is not None and rsi < rsi_buy_threshold and self.usdc_balance > 0:
                    amount_to_invest = self.usdc_balance * 0.2
                    if amount_to_invest >= min_trade_value:
                        amount_to_buy = amount_to_invest / current_price

                        if self.trader:
                            amount_to_buy = amount_to_invest / current_price
                            self.coin_balance += amount_to_buy
                            self.usdc_balance -= amount_to_invest
                            print(f"RSI BUY => bought {amount_to_buy:.6f} {self.coin_id.upper()} at ${current_price:.2f} (~${amount_to_buy * current_price:.2f})")
                            self.trader.trade("USDC_BASE", self.trader_coin, amount_to_invest, slippage=1)
                            self.log_trade("BUY", amount_to_buy, current_price)

                    else:
                        print(f"RSI BUY skipped: trade value ${amount_to_invest:.2f} < ${min_trade_value:.2f}")
                else:
                    print("No RSI buy condition.")

                # Sell
                if rsi is not None and rsi > rsi_sell_threshold and self.coin_balance > 0:
                    amount_to_sell = self.coin_balance * 0.2
                    trade_value = amount_to_sell * current_price
                    if trade_value >= min_trade_value:

                        if self.trader:
                            usdc_gained = trade_value
                            self.usdc_balance += usdc_gained
                            self.coin_balance -= amount_to_sell
                            print(f"RSI SELL => sold {amount_to_sell:.6f} {self.coin_id.upper()} at ${current_price:.2f} (~${amount_to_sell * current_price:.2f})")
                            self.trader.trade(self.trader_coin, "USDC_BASE", amount_to_sell, slippage=1)
                            self.log_trade("SELL", amount_to_sell, current_price)
                            
                    else:
                        print(f"RSI SELL skipped: trade value ${trade_value:.2f} < ${min_trade_value:.2f}")
                else:
                    print("No RSI sell condition.")

            final_value = self.get_portfolio_value(current_price)
            final_profit = final_value - self.initial_capital
            print(f"USDC Balance: ${self.usdc_balance:.2f} | {self.coin_id.upper()} Balance: {float(self.coin_balance):.6f} (~${float(self.coin_balance) * current_price:.2f})")
            print(f"Current Net Profit: ${final_profit:.2f}")
            print(f"Waiting {self.check_interval} seconds...\n")
            print("----------------------------------------------------------\n")
            time.sleep(self.check_interval)

    def print_final_summary(self, current_price):
        final_value = self.get_portfolio_value(current_price)
        final_profit = final_value - self.initial_capital
        print("\n==== BOT TERMINATED ====")
        print(f"Final Portfolio Value: ${final_value:.2f}")
        print(f"Final Net Profit: ${final_profit:.2f}")
        print(f"Final USDC Balance: ${self.usdc_balance:.2f}, Final {self.coin_id.upper()} Balance: {self.coin_balance:.6f} (~${self.coin_balance * current_price:.2f})")

    def get_usdc_balance(self):
        return self.trader.get_balance(self.wallet_address)
