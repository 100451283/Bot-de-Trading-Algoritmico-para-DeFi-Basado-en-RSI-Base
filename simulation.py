import requests
from advancedTradingBot import AdvancedTradingBot
from datetime import datetime
import matplotlib.pyplot as plt
import time
import json 

def fetch_historical_data(coin_id, days=5, interval='hourly'):
    """	If you use days=1, you get 5-minute intervals (good for high-frequency backtests).
	•	If you use days=5, you get hourly data points (~120 points).
	•	If you use days=90, you still get hourly data (~2160 points).
	•	If you go beyond 90 (e.g., 180), CoinGecko switches to daily candles (lower resolution)."""

    base_url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        'vs_currency': 'usd',
        'days': days
    }
    
    try:
        r = requests.get(base_url, params=params)
        r.raise_for_status()
        data = r.json()
        return data["prices"]
    
    except Exception as e:
        print(f"Error fetching market_chart data: {e}")
        return None

class BacktestBot(AdvancedTradingBot):
    """
    Extends the AdvancedTradingBot with a run_backtest method
    that iterates over a list of historical price points.
    """
    def run_backtest(self, historical_prices):

        AdvancedTradingBot.clear_trade_log()
        
        min_trade_value = 1.0  # Only buy/sell if trade is worth more than $1

        print(f"Starting BACKTEST for {self.coin_id} with {len(historical_prices)} data points...")
        
        for i, (timestamp, price) in enumerate(historical_prices):
            # Convert ms timestamp to a readable date 
            date_str = datetime.utcfromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')
            
            data = {
                'current_price': price,
                'volume_24h': 999999999  # artificially high, skip volume check
            }
            
            print(f"\nData point {i+1}/{len(historical_prices)} | {date_str}")
            current_price = data["current_price"]
            volume_24h = data["volume_24h"]
            print(f"Price: ${current_price:.2f}")

            # Append price for RSI
            self.price_history.append(current_price)
            if len(self.price_history) > (self.rsi_period + 1):
                self.price_history.pop(0)

            if self.baseline_price is None:
                self.baseline_price = current_price
                print(f"Baseline set to ${self.baseline_price:.2f}")

            # Calculate portfolio value & net profit
            portfolio_value = self.get_portfolio_value(current_price)
            net_profit = portfolio_value - self.initial_capital
            print(f"Portfolio Value: ${portfolio_value:.2f}, Net Profit: ${net_profit:.2f}")

            # RSI
            rsi = None
            if len(self.price_history) >= self.rsi_period:
                rsi = self.compute_rsi(self.price_history[-self.rsi_period:])
                if rsi is not None:
                    print(f"RSI({self.rsi_period}) = {rsi:.2f}")

            # Still compute percent_change but not necessarily use it
            percent_change = ((current_price - self.baseline_price) / self.baseline_price) * 100
            
            # Step 1: forced net profit check
            if self.coin_balance > 0:
                if net_profit >= self.profit_take:
                    print(f"Net profit >= {self.profit_take:.2f} => SELL ALL")
                    usdc_gained = self.coin_balance * current_price
                    self.usdc_balance += usdc_gained
                    self.log_trade("FULL_SELL_PROFIT", self.coin_balance, current_price)
                    self.coin_balance = 0
                    break
                elif net_profit <= self.profit_stop:
                    print(f"Net profit <= {self.profit_stop:.2f} => SELL ALL")
                    usdc_gained = self.coin_balance * current_price
                    self.usdc_balance += usdc_gained
                    self.log_trade("FULL_SELL_STOPLOSS", self.coin_balance, current_price)
                    self.coin_balance = 0
                    break

            # Step 2: partial RSI-based trades
            if volume_24h < 1_000_000:
                print("Volume too low, skipping RSI trades.")
            else:
                rsi_buy_threshold = 30 #CHANGE
                rsi_sell_threshold = 70 #CHANGE
                
                min_trade_value = 1.0  # Only buy/sell if trade is worth more than $1

                # Buy condition
                if rsi is not None and rsi < rsi_buy_threshold and self.usdc_balance > 0:
                    amount_to_invest = self.usdc_balance * 0.2
                    if amount_to_invest >= min_trade_value:
                        amount_to_buy = amount_to_invest / current_price
                        self.coin_balance += amount_to_buy
                        self.usdc_balance -= amount_to_invest
                        print(f"RSI BUY => bought {amount_to_buy:.6f} {self.coin_id.upper()} at ${current_price:.2f} (~${amount_to_buy * current_price:.2f})")
                        self.log_trade("BUY", amount_to_buy, current_price)
                    else:
                        print(f"RSI BUY skipped: trade value ${amount_to_invest:.2f} < ${min_trade_value:.2f}")
                else:
                    print("No RSI buy condition.")

                # Sell condition
                if rsi is not None and rsi > rsi_sell_threshold and self.coin_balance > 0:
                    amount_to_sell = self.coin_balance * 0.2
                    trade_value = amount_to_sell * current_price
                    if trade_value >= min_trade_value:
                        usdc_gained = trade_value
                        self.usdc_balance += usdc_gained
                        self.coin_balance -= amount_to_sell
                        print(f"RSI SELL => sold {amount_to_sell:.6f} {self.coin_id.upper()} at ${current_price:.2f} (~${amount_to_sell * current_price:.2f})")
                        self.log_trade("SELL", amount_to_sell, current_price)
                    else:
                        print(f"RSI SELL skipped: trade value ${trade_value:.2f} < ${min_trade_value:.2f}")
                else:
                    print("No RSI sell condition.")
                print(f"{self.coin_id.upper()} Balance: {self.coin_balance:.6f} (~${self.coin_balance * current_price:.2f}), USDC Balance: ${self.usdc_balance:.2f}")

        # After the loop, print final stats:
        final_value = self.get_portfolio_value(self.price_history[-1])
        final_profit = final_value - self.initial_capital
        print("\n==== BACKTEST COMPLETE ====")
        print(f"Final Portfolio Value: ${final_value:.2f}")
        print(f"Final Net Profit: ${final_profit:.2f}")
        print(f"Final USDC Balance: ${self.usdc_balance:.2f}, Final {self.coin_id.upper()} Balance:  {self.coin_balance:.6f} (~${self.coin_balance * current_price:.2f})")


    def plot(self):
        initial_balance_usdc = 100.0
        wallet = "0xDemoAddress"
        trades_file = "trades.json"

        try:
            with open(trades_file, "r") as f:
                lines = f.readlines()
        except FileNotFoundError:
            print("trades.json file not found.")
            return

        balance_usdc = initial_balance_usdc
        coin_balance = 0.0
        values = []
        timestamps = []

        for line in lines:
            trade = json.loads(line.strip())
            if trade["wallet"] != wallet:
                continue

            timestamp = datetime.utcfromtimestamp(trade["timestamp"])
            price = trade["price"]
            amount = trade["amount"]

            if trade["action"] == "BUY":
                cost = price * amount
                coin_balance += amount
                balance_usdc -= cost
            elif trade["action"] == "SELL":
                coin_balance -= amount
                balance_usdc += price * amount

            total_value = balance_usdc + coin_balance * price
            timestamps.append(timestamp)
            values.append(total_value)

        plt.figure(figsize=(10, 5))
        plt.plot(timestamps, values, marker='o', linestyle='-')
        plt.title("Portfolio Value Over Time")
        plt.xlabel("Time")
        plt.ylabel("Total Value in USDC")
        plt.grid(True)
        plt.tight_layout()
        plt.xticks(rotation=45)
        plt.show()


def main():

    #https://api.coingecko.com/api/v3/coins/list -> for coin names
    #Reference coins -> ETH (ethereum), AERO (aerodrome-finance), Dege (degen-base)

    coin_id = "bitcoin"  # Reference coins -> bitcoin, ethereum, degen-base, aerodrome-finance
    historical_data = fetch_historical_data(coin_id, days=90, interval='hourly')
    
    if not historical_data:
        print("No historical data fetched. Exiting.")
        return
    
    bot = BacktestBot(
        coin_id=coin_id,
        profit_take=10,   # e.g., +$10 net profit => sell all
        profit_stop=-10, # e.g., -$10 net => sell all
        initial_balance_usdc=100.0,
        wallet_address="0xDemoAddress"
    )
    
    bot.run_backtest(historical_data)

    time.sleep(2)

    bot.plot()

if __name__ == "__main__":
    main()