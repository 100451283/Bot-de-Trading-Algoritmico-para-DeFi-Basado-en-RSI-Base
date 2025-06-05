from advancedTradingBot import AdvancedTradingBot  
import sys

class Front:
    def __init__(self):
        print("=== Welcome to the Trading Bot CLI ===\n")

        wallet_address = input("1. Enter your wallet address: ").strip()
        private_key = input("2. Enter your private key: ").strip()

        try:
            initial_balance = float(input("3. Enter your initial USDC balance you would like to trade with (e.g., 100): "))
            profit_take = float(input("4. Enter your profit take target (e.g., 10): "))
            profit_stop = float(input("5. Enter your stop loss (e.g., -10): "))
        except ValueError:
            print("Invalid number input. Exiting.")
            sys.exit(1)

        print("\n6. Choose the coin to trade:")
        print("   1. Ethereum")
        print("   2. Degen Base")
        print("   3. Aerodrome Finance")

        coin_map = {
            "1": "ethereum",
            "2": "degen-base",
            "3": "aerodrome-finance"
        }

        coin_choice = input("Enter choice (1, 2, or 3): ").strip()
        coin_id = coin_map.get(coin_choice)

        if not coin_id:
            print("Invalid coin selection. Exiting.")
            sys.exit(1)

        print(f"\n✅ Launching bot for {coin_id.upper()} with ${initial_balance:.2f} USDC...\n")

        try:
            bot = AdvancedTradingBot(
                coin_id=coin_id,
                profit_take=profit_take,
                profit_stop=profit_stop,
                initial_balance_usdc=initial_balance,
                wallet_address=wallet_address,
                private_key=private_key
            )
            value = bot.get_usdc_balance()

            if value < initial_balance:
                print(f"❌ Insufficient USDC balance. Required: ${initial_balance:.2f}, found: ${value:.2f}")
                print("Please top up your wallet and restart the bot.")
                sys.exit(1)

            eth_balance = bot.trader.get_balance(wallet_address, token_symbol=None)
            if eth_balance < 0.0005:
                print(f"⚠️ Warning: ETH balance is very low (${eth_balance:.5f}). You may not be able to pay gas fees.")
                print("Please top up your wallet and restart the bot.")
                sys.exit(1)

            bot.run()
            # If run() ends (breaks from loop), show final summary
            if bot.price_history:
                bot.print_final_summary(bot.price_history[-1])
        except KeyboardInterrupt:
            print("\n🔴 Bot manually interrupted.")
            if bot.price_history:
                bot.print_final_summary(bot.price_history[-1])
            else:
                print("No trading data collected. Goodbye.")