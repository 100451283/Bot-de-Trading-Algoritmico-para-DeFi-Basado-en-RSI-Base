import json
import time
from web3 import Web3
import logging
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class UniswapTrader:
    def __init__(self, wallet_address, private_key):
        alchemy_url = "https://base-mainnet.g.alchemy.com/v2/z9EyEduaDQJpEvG52cqnre3aLpW7yH8h"
        uniswap_router_address = "0x4752ba5dbc23f44d87826276bf6fd6b1c372ad24"
        token_file = "tokens.json"
            
        self.web3 = Web3(Web3.HTTPProvider(alchemy_url))
        self.wallet_address = Web3.to_checksum_address(wallet_address)
        self.private_key = private_key
        self.router_address = Web3.to_checksum_address(uniswap_router_address)

        # Check connection
        if self.web3.is_connected():
            print("Conectado a Base exitosamente ✅")
        else:
            raise ConnectionError("No se pudo conectar a la red Base ❌")

        # Load tokens from JSON
        with open(token_file) as f:
            self.tokens = json.load(f)

        # Load Uniswap Router ABI
        with open("uni_abi.json") as f:
            self.uniswap_abi = json.load(f)

        # Initialize Uniswap contract
        self.contract = self.web3.eth.contract(address=self.router_address, abi=self.uniswap_abi)

    def get_token(self, symbol):
        """Retrieve token details from the JSON file."""
        if symbol not in self.tokens:
            raise ValueError(f"Token {symbol} not found in the token file.")
        token = self.tokens[symbol]
        token['address'] = Web3.to_checksum_address(token['address'])
        return token

    def buy_token(self, amount_eth, token_symbol, slippage=1):
        """Swaps ETH for a given token on Uniswap V2."""
        try: 
            token = self.get_token(token_symbol)
            path = [self.get_token("WETH_BASE")['address'], token['address']]
            amount_out_min = self.contract.functions.getAmountsOut(amount_eth, path).call()[-1]
            amount_out_min = int(amount_out_min * (1 - slippage / 100))

            tx = self.contract.functions.swapExactETHForTokens(
                amount_out_min, path, self.wallet_address, int(time.time()) + 60
            ).build_transaction({
                'from': self.wallet_address,
                'value': amount_eth,
                'gasPrice': self.web3.eth.gas_price,
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address, "pending")
            })

            try:
                gas_limit = self.web3.eth.estimate_gas(tx)
                tx['gas'] = gas_limit + 10000
            except Exception as e:
                print(f"⚠️ Gas estimation failed: {e}, using fallback gas limit")
                tx['gas'] = 300000  # Fallback gas limit

            signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"✅ Transaction sent: {self.web3.to_hex(tx_hash)}")

            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            if receipt is None or receipt.status != 1:
                raise Exception(f"Transaction failed or not confirmed: {tx_hash.hex()}")
            print(f"✅ Transaction confirmed in block {receipt.blockNumber}")
        except Exception as e:
            print(f"Error buying token: {e}")
            raise Exception(f"Error buying token: {e}")

    def sell_token(self, amount_token, token_symbol, slippage=1):
        """Swaps a given token for ETH on Uniswap V2."""
        try: 
            self.approve_token(token_symbol, amount_token)  # Approve the token if not already approved
            token = self.get_token(token_symbol)
            path = [token['address'], self.get_token("WETH_BASE")['address']]
            amount_out_min = self.contract.functions.getAmountsOut(amount_token, path).call()[-1]
            amount_out_min = int(amount_out_min * (1 - slippage / 100))

            tx = self.contract.functions.swapExactTokensForETH(
                amount_token, amount_out_min, path, self.wallet_address, int(time.time()) + 60
            ).build_transaction({
                'from': self.wallet_address,
                'gasPrice': self.web3.eth.gas_price,
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address, "pending"),
            })

            # Estimate gas limit
            gas_limit = self.web3.eth.estimate_gas(tx)
            tx['gas'] = gas_limit + 10000 # Add 10k gas buffer

            signed_tx = self.web3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.web3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"✅ Transaction sent: {self.web3.to_hex(tx_hash)}")

            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            if receipt is None or receipt.status != 1:
                raise Exception(f"Transaction failed or not confirmed: {tx_hash.hex()}")
            
            print(f"✅ Transaction confirmed in block {receipt.blockNumber}")
            return amount_out_min
        except Exception as e:
            print(f"Error selling token: {e}")
            raise Exception(f"Error selling token: {e}")
            

    def approve_token(self, token_symbol, amount_required=None):
        """
        Approves Uniswap to spend a token if not already approved.
        If amount_required is None, approves the max value.
        """
        try:
            token = self.get_token(token_symbol)
            token_contract = self.web3.eth.contract(address=token['address'], abi=token['abi'])

            max_approval = 2**256 - 1
            required = amount_required or max_approval

            current_allowance = token_contract.functions.allowance(self.wallet_address, self.router_address).call()

            if current_allowance >= required:
                print(f"✅ Token {token_symbol} is already approved (allowance: {current_allowance})")
                return  # No approval needed

            print(f"🔓 Approving {token_symbol} (current allowance: {current_allowance})...")

            approve_tx = token_contract.functions.approve(self.router_address, max_approval).build_transaction({
                'from': self.wallet_address,
                'gasPrice': self.web3.eth.gas_price,
                'nonce': self.web3.eth.get_transaction_count(self.wallet_address, "pending"),
            })

            gas_limit = self.web3.eth.estimate_gas(approve_tx)
            approve_tx['gas'] = gas_limit + 10000 # Add 10k gas buffer

            signed_approve_tx = self.web3.eth.account.sign_transaction(approve_tx, self.private_key)
            approve_tx_hash = self.web3.eth.send_raw_transaction(signed_approve_tx.raw_transaction)

            print(f"🚀 Approval transaction sent: {self.web3.to_hex(approve_tx_hash)}")
            self.web3.eth.wait_for_transaction_receipt(approve_tx_hash)
            print("✅ Approval confirmed.")

            receipt = self.web3.eth.wait_for_transaction_receipt(approve_tx_hash)
            print(f"✅ Transaction confirmed in block {receipt.blockNumber}")
        except Exception as e:
            print(f"Error approving token: {e}")
    
    def monitor_transaction(self, tx_hash, timeout=120):
        """Monitors the status of a transaction."""
        try:
            receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
            if receipt['status'] == 1:
                print(f"✅ Transaction confirmed in block {receipt.blockNumber}")
                return receipt
            else:
                print(f"❌ Transaction failed in block {receipt.blockNumber}")
                return None
        except Exception as e:
            print(f"Error monitoring transaction: {e}")
            return None
        
    def get_balance(self, address, token_symbol="USDC_BASE"):
        """Gets the balance of a specific token or ETH for the given address."""
        # Convert the address to checksum format
        checksum_address = self.web3.to_checksum_address(address)

        if token_symbol is None:
            balance_wei = self.web3.eth.get_balance(checksum_address)
            balance_eth = self.web3.from_wei(balance_wei, 'ether')
            return balance_eth
        else:
            token = self.get_token(token_symbol)
            token_contract = self.web3.eth.contract(address=token['address'], abi=token['abi'])
            
            balance = token_contract.functions.balanceOf(checksum_address).call()
            
            decimals = token.get('decimals', 18)  # Default to 18 decimals if not specified
            return balance / (10 ** decimals)
        
    def trade(self, input_token_symbol, output_token_symbol, amount, slippage=1):
        """
        Generalized trade function that supports non-ETH token swaps.
        Steps:
        1. If input ≠ ETH, sell input for ETH.
        2. If output ≠ ETH, buy output using ETH.
        
        :param input_token_symbol: Token you are selling (e.g., "USDC_BASE")
        :param output_token_symbol: Token you are buying (e.g., "DEGEN")
        :param amount: Amount of input token (raw units, e.g., USDC = 6 decimals)
        """
        WETH = "WETH_BASE"

        input_token = self.get_token(input_token_symbol)
        input_decimals = input_token.get("decimals", 18)
        amount = int(amount * (10 ** input_decimals))
        
        if input_token_symbol != WETH:
            print(f"🔄 Step 1: Swapping {input_token_symbol} → ETH...")
            eth_amount = self.retry_until_success(
                self.sell_token, amount, input_token_symbol, slippage=slippage
            )

            # Optional: wait a bit for confirmation
            time.sleep(5)
        else:
            eth_amount = amount  # If input is ETH, use directly

        if output_token_symbol != WETH:
            print(f"🔄 Step 2: Swapping ETH → {output_token_symbol}...")
            self.retry_until_success(
                self.buy_token, eth_amount, output_token_symbol, slippage=slippage
            )
        else:
            print("✅ Output is ETH, no need for second swap.")

    def retry_until_success(self, func, *args, retries=5, delay=10, **kwargs):
        for attempt in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"⚠️ Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    sleep_time = delay + random.randint(0, 5)
                    print(f"🔁 Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    print("❌ All retry attempts failed.")
                    raise


