"""
attack.py — Demo attack script
Simulates a rug pull attack on MockProtocol for demo purposes.
Run this during the demo to trigger the agent's emergency response.
Usage: python attack.py
"""

from web3 import Web3
from dotenv import load_dotenv
import os
import sys
import json
import time

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

MONAD_RPC_URL = os.getenv("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
MOCK_PROTOCOL_ADDRESS = os.getenv("MOCK_PROTOCOL_ADDRESS")

DEAD_ADDRESS = "0x000000000000000000000000000000000000dEaD"

def load_abi(contract_name):
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'out')
    abi_path = os.path.join(out_dir, f"{contract_name}.sol", f"{contract_name}.json")
    if not os.path.exists(abi_path):
        print(f"[ERROR] ABI not found: {abi_path}")
        print("Run 'forge build' from the project root first.")
        sys.exit(1)
    with open(abi_path) as f:
        return json.load(f)["abi"]

def send_tx(w3, deployer, tx_data, description):
    nonce = w3.eth.get_transaction_count(deployer.address)
    tx = tx_data.build_transaction({
        'from': deployer.address,
        'nonce': nonce,
        'gas': 300000,
        'gasPrice': w3.eth.gas_price,
        'chainId': 10143,
    })
    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    print(f"  TX sent: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    status = "SUCCESS" if receipt['status'] == 1 else "FAILED"
    print(f"  Status: {status} | Block: {receipt['blockNumber']}")
    print(f"  Explorer: https://testnet.monadexplorer.com/tx/{tx_hash.hex()}")
    return tx_hash.hex(), receipt['status'] == 1

def attack():
    print("=" * 55)
    print("  DEMO ATTACK SCRIPT — Protocol Vital Signs")
    print("  Simulating rug pull on MockProtocol...")
    print("=" * 55)

    if not PRIVATE_KEY or PRIVATE_KEY == "your_deployer_private_key_here":
        print("[ERROR] PRIVATE_KEY not set in .env")
        sys.exit(1)

    if not MOCK_PROTOCOL_ADDRESS or MOCK_PROTOCOL_ADDRESS == "filled_after_deployment":
        print("[ERROR] MOCK_PROTOCOL_ADDRESS not set in .env")
        sys.exit(1)

    w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
    if not w3.is_connected():
        print(f"[ERROR] Cannot connect to Monad RPC: {MONAD_RPC_URL}")
        sys.exit(1)

    deployer = w3.eth.account.from_key(PRIVATE_KEY)
    print(f"\n  Attacker wallet: {deployer.address}")

    mock_protocol_abi = load_abi("MockProtocol")
    mock_protocol = w3.eth.contract(
        address=Web3.to_checksum_address(MOCK_PROTOCOL_ADDRESS),
        abi=mock_protocol_abi
    )

    # Read current state
    current_tvl = mock_protocol.functions.getTVL().call()
    current_liquidity = mock_protocol.functions.getLiquidity().call()
    print(f"\n  Current TVL:       {current_tvl // 10**18} VLT")
    print(f"  Current Liquidity: {current_liquidity // 10**18} VLT")

    print("\n  Waiting 3 seconds so audience can see healthy state...")
    time.sleep(3)

    # ── Attack Step 1: Drain 40% of TVL ──────────────────────────────────────
    print("\n" + "-" * 55)
    print("  STEP 1: Admin draining 40% of TVL to dead address...")
    drain_amount = int(current_tvl * 0.4) if current_tvl > 0 else 400 * 10**18
    if drain_amount == 0:
        drain_amount = 400 * 10**18
    print(f"  Draining {drain_amount // 10**18} VLT to {DEAD_ADDRESS[:12]}...")

    _, step1_ok = send_tx(
        w3, deployer,
        mock_protocol.functions.adminTransferFunds(DEAD_ADDRESS, drain_amount),
        "adminTransferFunds"
    )

    if step1_ok:
        new_tvl = mock_protocol.functions.getTVL().call()
        print(f"  TVL after drain: {new_tvl // 10**18} VLT (was {current_tvl // 10**18} VLT)")

    print("\n  Waiting 5 seconds before step 2...")
    time.sleep(5)

    # ── Attack Step 2: Remove 30% of liquidity ────────────────────────────────
    print("\n" + "-" * 55)
    print("  STEP 2: Removing 30% of liquidity pool...")
    remove_amount = int(current_liquidity * 0.3) if current_liquidity > 0 else 150 * 10**18
    if remove_amount == 0:
        remove_amount = 150 * 10**18
    print(f"  Removing {remove_amount // 10**18} VLT from liquidity...")

    _, step2_ok = send_tx(
        w3, deployer,
        mock_protocol.functions.removeLiquidity(remove_amount),
        "removeLiquidity"
    )

    if step2_ok:
        new_liquidity = mock_protocol.functions.getLiquidity().call()
        print(f"  Liquidity after: {new_liquidity // 10**18} VLT (was {current_liquidity // 10**18} VLT)")

    print("\n" + "=" * 55)
    print("  ATTACK COMPLETE")
    print("  The AI agent will detect this on its next check.")
    print("  Watch the agent terminal for EMERGENCY diagnosis.")
    print("  Evacuation will trigger automatically.")
    print("=" * 55)


if __name__ == "__main__":
    attack()
