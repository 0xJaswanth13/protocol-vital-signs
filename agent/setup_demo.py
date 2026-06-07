"""
setup_demo.py — Deposit user funds into MockProtocol for the demo.
Two users each deposit 1000 VLT. On emergency, the agent drains
all remaining TVL to the backup wallet.
"""

from web3 import Web3
from dotenv import load_dotenv
import json, os, sys

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

w3 = Web3(Web3.HTTPProvider(os.getenv("MONAD_RPC_URL")))
if not w3.is_connected():
    print("[ERROR] Cannot connect to Monad"); sys.exit(1)

def load_abi(name):
    path = os.path.join(os.path.dirname(__file__), '..', 'out', f'{name}.sol', f'{name}.json')
    with open(path) as f:
        return json.load(f)["abi"]

deployer   = w3.eth.account.from_key(os.getenv("PRIVATE_KEY"))
agent_acct = w3.eth.account.from_key(os.getenv("AGENT_PRIVATE_KEY"))
backup     = Web3.to_checksum_address(os.getenv("BACKUP_WALLET"))

token    = w3.eth.contract(address=Web3.to_checksum_address(os.getenv("MOCK_TOKEN_ADDRESS")),    abi=load_abi("MockToken"))
protocol = w3.eth.contract(address=Web3.to_checksum_address(os.getenv("MOCK_PROTOCOL_ADDRESS")), abi=load_abi("MockProtocol"))

DEPOSIT = 1000 * 10**18

def send(acct, pk, fn, label, gas=300000):
    nonce  = w3.eth.get_transaction_count(acct.address)
    tx     = fn.build_transaction({"from": acct.address, "nonce": nonce,
                                   "gas": gas, "gasPrice": w3.eth.gas_price, "chainId": 10143})
    signed = w3.eth.account.sign_transaction(tx, pk)
    txh    = w3.eth.send_raw_transaction(signed.rawTransaction)
    r      = w3.eth.wait_for_transaction_receipt(txh, timeout=60)
    status = "OK" if r["status"] == 1 else "FAIL"
    print(f"  [{status}] {label}  tx={txh.hex()[:16]}...")
    return r["status"] == 1

print("=" * 55)
print("  Demo Setup — Protocol Vital Signs Agent")
print("=" * 55)

# User 1: Deployer
print(f"\nUser 1 (deployer): {deployer.address}")
send(deployer, os.getenv("PRIVATE_KEY"), token.functions.mint(deployer.address, DEPOSIT), "Mint 1000 VLT")
send(deployer, os.getenv("PRIVATE_KEY"),
     token.functions.approve(Web3.to_checksum_address(os.getenv("MOCK_PROTOCOL_ADDRESS")), DEPOSIT),
     "Approve MockProtocol")
send(deployer, os.getenv("PRIVATE_KEY"), protocol.functions.deposit(DEPOSIT), "Deposit 1000 VLT into MockProtocol")

# User 2: Agent wallet
print(f"\nUser 2 (agent):    {agent_acct.address}")
send(deployer, os.getenv("PRIVATE_KEY"), token.functions.mint(agent_acct.address, DEPOSIT), "Mint 1000 VLT")
send(agent_acct, os.getenv("AGENT_PRIVATE_KEY"),
     token.functions.approve(Web3.to_checksum_address(os.getenv("MOCK_PROTOCOL_ADDRESS")), DEPOSIT),
     "Approve MockProtocol")
send(agent_acct, os.getenv("AGENT_PRIVATE_KEY"), protocol.functions.deposit(DEPOSIT), "Deposit 1000 VLT into MockProtocol")

# Final status
print("\n" + "=" * 55)
tvl = protocol.functions.getTVL().call() // 10**18
liq = protocol.functions.getLiquidity().call() // 10**18
print(f"  MockProtocol TVL:       {tvl} VLT")
print(f"  MockProtocol Liquidity: {liq} VLT")
print(f"  Backup wallet:          {backup}")
print("\n  Setup complete! Start the agent:")
print("  python3 agent/agent.py")
print("=" * 55)
