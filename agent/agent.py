"""
Protocol Vital Signs Agent
Watches MockProtocol's 5 vital signs, uses OpenAI to diagnose risk,
and drains remaining funds to a safe backup wallet on EMERGENCY.
"""

from web3 import Web3
from openai import OpenAI
import time
import json
import os
import sys
from datetime import datetime
from config import (
    MONAD_RPC_URL, AGENT_PRIVATE_KEY, OPENAI_API_KEY,
    MOCK_PROTOCOL_ADDRESS, BACKUP_WALLET,
    CHECK_INTERVAL, TVL_WARNING_THRESHOLD, TVL_CRITICAL_THRESHOLD,
    LIQUIDITY_WARNING_THRESHOLD, LIQUIDITY_CRITICAL_THRESHOLD,
    TX_WARNING_MULTIPLIER, TX_CRITICAL_MULTIPLIER
)

# ─── Startup validation ───────────────────────────────────────────────────────
def validate_config():
    missing = []
    if not AGENT_PRIVATE_KEY:   missing.append("AGENT_PRIVATE_KEY")
    if not OPENAI_API_KEY:      missing.append("OPENAI_API_KEY")
    if not MOCK_PROTOCOL_ADDRESS: missing.append("MOCK_PROTOCOL_ADDRESS")
    if not BACKUP_WALLET:       missing.append("BACKUP_WALLET")
    if missing:
        print(f"[ERROR] Missing .env values: {', '.join(missing)}")
        sys.exit(1)

validate_config()

# ─── Web3 setup ───────────────────────────────────────────────────────────────
w3 = Web3(Web3.HTTPProvider(MONAD_RPC_URL))
if not w3.is_connected():
    print(f"[ERROR] Cannot connect to Monad RPC: {MONAD_RPC_URL}")
    sys.exit(1)

agent_account = w3.eth.account.from_key(AGENT_PRIVATE_KEY)

def load_abi(contract_name):
    base = os.path.dirname(__file__)
    # abis/ is committed to repo — works on Render without forge build
    abis_path = os.path.join(base, '..', 'abis', f"{contract_name}.json")
    if os.path.exists(abis_path):
        with open(abis_path) as f:
            return json.load(f)
    # Fallback: local dev after forge build
    out_path = os.path.join(base, '..', 'out', f"{contract_name}.sol", f"{contract_name}.json")
    if os.path.exists(out_path):
        with open(out_path) as f:
            return json.load(f)["abi"]
    print(f"[ERROR] ABI not found for {contract_name}.")
    sys.exit(1)

mock_protocol = w3.eth.contract(
    address=Web3.to_checksum_address(MOCK_PROTOCOL_ADDRESS),
    abi=load_abi("MockProtocol")
)
backup_wallet = Web3.to_checksum_address(BACKUP_WALLET)

client = OpenAI(api_key=OPENAI_API_KEY)

# ─── In-memory history ────────────────────────────────────────────────────────
tvl_history       = []
liquidity_history = []
tx_count_history  = []
previous_owner    = None

# ─── Vital sign checkers ──────────────────────────────────────────────────────

def check_tvl():
    try:
        current_tvl = mock_protocol.functions.getTVL().call()
        tvl_history.append(current_tvl)

        if len(tvl_history) < 2:
            print(f"  TVL: {current_tvl // 10**18} VLT | Status: NORMAL (baseline)")
            return "NORMAL", current_tvl, 0

        previous_tvl = tvl_history[-2]
        if previous_tvl == 0:
            print(f"  TVL: {current_tvl // 10**18} VLT | Status: NORMAL")
            return "NORMAL", current_tvl, 0

        pct_change = ((previous_tvl - current_tvl) / previous_tvl) * 100
        status = "CRITICAL" if pct_change >= TVL_CRITICAL_THRESHOLD else \
                 "WARNING"  if pct_change >= TVL_WARNING_THRESHOLD  else "NORMAL"

        print(f"  TVL: {current_tvl // 10**18} VLT | Drop: {pct_change:.1f}% | Status: {status}")
        return status, current_tvl, pct_change
    except Exception as e:
        print(f"  TVL check error: {e}")
        return "NORMAL", 0, 0


def check_admin_wallet():
    try:
        latest_block = w3.eth.block_number
        from_block   = max(0, latest_block - 20)
        events = mock_protocol.events.AdminTransfer.get_logs(fromBlock=from_block, toBlock='latest')

        if len(events) > 0:
            latest_event = events[-1]
            amount       = latest_event['args']['amount']
            to_address   = latest_event['args']['to']
            if amount > 100 * 10**18:
                status = "CRITICAL"
                desc   = f"Admin transferred {amount // 10**18} VLT to {to_address[:10]}..."
            else:
                status = "WARNING"
                desc   = f"Admin made small transfer to {to_address[:10]}..."
        else:
            status = "NORMAL"
            desc   = "No recent admin activity"

        print(f"  Admin: {desc} | Status: {status}")
        return status, desc
    except Exception as e:
        print(f"  Admin check error: {e}")
        return "NORMAL", "No admin activity detected"


def check_liquidity():
    try:
        current_liq = mock_protocol.functions.getLiquidity().call()
        liquidity_history.append(current_liq)

        if len(liquidity_history) < 2:
            print(f"  Liquidity: {current_liq // 10**18} VLT | Status: NORMAL (baseline)")
            return "NORMAL", current_liq, 0

        prev_liq = liquidity_history[-2]
        if prev_liq == 0:
            return "NORMAL", current_liq, 0

        pct_change = ((prev_liq - current_liq) / prev_liq) * 100
        status = "CRITICAL" if pct_change >= LIQUIDITY_CRITICAL_THRESHOLD else \
                 "WARNING"  if pct_change >= LIQUIDITY_WARNING_THRESHOLD  else "NORMAL"

        print(f"  Liquidity: {current_liq // 10**18} VLT | Drop: {pct_change:.1f}% | Status: {status}")
        return status, current_liq, pct_change
    except Exception as e:
        print(f"  Liquidity check error: {e}")
        return "NORMAL", 0, 0


def check_transaction_pattern():
    try:
        current_tx = mock_protocol.functions.getTransactionCount().call()
        tx_count_history.append(current_tx)

        if len(tx_count_history) < 3:
            print(f"  TX Count: {current_tx} | Status: NORMAL (building baseline)")
            return "NORMAL", current_tx

        prev    = tx_count_history[:-1]
        avg_inc = (prev[-1] - prev[0]) / len(prev) if len(prev) >= 2 else 0
        cur_inc = current_tx - tx_count_history[-2]

        if avg_inc > 0:
            mult   = cur_inc / avg_inc
            status = "CRITICAL" if mult >= TX_CRITICAL_MULTIPLIER else \
                     "WARNING"  if mult >= TX_WARNING_MULTIPLIER  else "NORMAL"
        else:
            status = "NORMAL"

        print(f"  TX Pattern: {cur_inc} new txs | Status: {status}")
        return status, current_tx
    except Exception as e:
        print(f"  TX pattern check error: {e}")
        return "NORMAL", 0


def check_contract_upgrades():
    global previous_owner
    try:
        current_owner = mock_protocol.functions.owner().call()
        if previous_owner is None:
            previous_owner = current_owner
            print(f"  Upgrades: Owner = {current_owner[:10]}... | Status: NORMAL (baseline)")
            return "NORMAL", "No upgrade detected"

        if current_owner != previous_owner:
            previous_owner = current_owner
            desc = f"Ownership changed to {current_owner[:10]}..."
            print(f"  Upgrades: {desc} | Status: ALERT")
            return "ALERT", desc

        print(f"  Upgrades: No change | Status: NORMAL")
        return "NORMAL", "No upgrade detected"
    except Exception as e:
        print(f"  Upgrade check error: {e}")
        return "NORMAL", "No upgrade detected"


# ─── AI diagnosis ─────────────────────────────────────────────────────────────

def get_ai_diagnosis(tvl_status, tvl_change, admin_status, admin_desc,
                      liquidity_status, liquidity_change, tx_status, upgrade_status):

    prompt = f"""You are a DeFi security analyst monitoring a protocol's health.
Analyze these 5 vital signs and give a security assessment.

VITAL SIGNS:
1. TVL: {tvl_status} — dropped {tvl_change:.1f}% since last check
2. Admin Wallet: {admin_status} — {admin_desc}
3. Liquidity: {liquidity_status} — changed {liquidity_change:.1f}%
4. Transaction Pattern: {tx_status}
5. Contract Ownership: {upgrade_status}

Respond in EXACTLY this format:
RISK_LEVEL: [HEALTHY | WARNING | CRITICAL | EMERGENCY]
DIAGNOSIS: [2-3 sentences explaining what is happening]
ACTION: [what users should do right now]

Rules:
- HEALTHY: All vitals normal
- WARNING: 1-2 vitals showing mild anomalies
- CRITICAL: 2-3 vitals showing serious anomalies
- EMERGENCY: 3+ vitals critical simultaneously — likely rug pull"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3
        )
        text = response.choices[0].message.content

        risk_level = "WARNING"
        diagnosis  = "Unable to generate diagnosis"
        action     = "Monitor the protocol closely"

        for line in text.strip().split('\n'):
            line = line.strip()
            if line.startswith("RISK_LEVEL:"):
                risk_level = line.replace("RISK_LEVEL:", "").strip()
            elif line.startswith("DIAGNOSIS:"):
                diagnosis  = line.replace("DIAGNOSIS:", "").strip()
            elif line.startswith("ACTION:"):
                action     = line.replace("ACTION:", "").strip()

        if risk_level not in ["HEALTHY", "WARNING", "CRITICAL", "EMERGENCY"]:
            risk_level = "WARNING"

        full_diagnosis = f"{diagnosis} Recommended: {action}"

        print(f"\n  OpenAI Diagnosis:")
        print(f"  Risk Level: {risk_level}")
        print(f"  {diagnosis}")
        print(f"  Action: {action}")

        return risk_level, full_diagnosis

    except Exception as e:
        print(f"  [WARN] OpenAI error: {e} — using fallback")
        criticals = sum([
            tvl_status      == "CRITICAL",
            admin_status    == "CRITICAL",
            liquidity_status == "CRITICAL",
            tx_status       == "CRITICAL",
        ])
        if criticals >= 3:
            return "EMERGENCY", "FALLBACK: Multiple critical vitals detected. Possible rug pull in progress. Recommended: Evacuate immediately."
        elif criticals >= 2:
            return "CRITICAL",  "FALLBACK: Multiple serious anomalies detected. Recommended: Consider withdrawing funds now."
        elif criticals >= 1:
            return "WARNING",   "FALLBACK: Anomaly detected. Recommended: Monitor closely."
        else:
            return "HEALTHY",   "FALLBACK: All vitals normal. Recommended: Continue monitoring."


# ─── Emergency evacuation ─────────────────────────────────────────────────────

def evacuate_funds():
    print("\n" + "!" * 60)
    print("  EMERGENCY EVACUATION — draining MockProtocol to backup wallet")
    print(f"  Backup: {backup_wallet}")
    print("!" * 60)

    try:
        tvl = mock_protocol.functions.getTVL().call()
        if tvl == 0:
            print("  [WARN] TVL is already 0. Nothing to drain.")
            return None

        print(f"  Draining {tvl // 10**18} VLT to backup wallet...")

        nonce = w3.eth.get_transaction_count(agent_account.address)
        fn    = mock_protocol.functions.agentDrainAll(backup_wallet)
        try:
            gas_limit = int(fn.estimate_gas({'from': agent_account.address}) * 1.5)
        except Exception:
            gas_limit = 300_000

        tx = fn.build_transaction({
            'from': agent_account.address,
            'nonce': nonce,
            'gas': gas_limit,
            'gasPrice': w3.eth.gas_price,
            'chainId': 10143,
        })

        signed  = w3.eth.account.sign_transaction(tx, AGENT_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        if receipt['status'] == 1:
            remaining = mock_protocol.functions.getTVL().call()
            print(f"\n  [SUCCESS] Evacuation complete!")
            print(f"  TX:    https://testnet.monadexplorer.com/tx/{tx_hash.hex()}")
            print(f"  MockProtocol TVL remaining: {remaining // 10**18} VLT")
            print(f"  Funds safe in backup wallet: {backup_wallet}")
        else:
            print(f"  [FAIL] Evacuation tx failed. TX: {tx_hash.hex()}")

        return tx_hash.hex()

    except Exception as e:
        print(f"  [ERROR] Evacuation failed: {e}")
        return None


# ─── Main loop ────────────────────────────────────────────────────────────────

def run_agent():
    print("=" * 60)
    print("  Protocol Vital Signs Agent — STARTED")
    print(f"  Protocol:     {MOCK_PROTOCOL_ADDRESS}")
    print(f"  Backup Wallet:{backup_wallet}")
    print(f"  Agent Wallet: {agent_account.address}")
    print(f"  Check Every:  {CHECK_INTERVAL}s")
    print("=" * 60)

    check_count = 0

    while True:
        check_count += 1
        print(f"\n{'='*60}")
        print(f"  VITAL SIGNS CHECK #{check_count} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        print("\n[1/5] TVL")
        tvl_status, current_tvl, tvl_change = check_tvl()

        print("\n[2/5] Admin Wallet")
        admin_status, admin_desc = check_admin_wallet()

        print("\n[3/5] Liquidity")
        liquidity_status, current_liq, liq_change = check_liquidity()

        print("\n[4/5] Transaction Pattern")
        tx_status, current_tx = check_transaction_pattern()

        print("\n[5/5] Contract Ownership")
        upgrade_status, upgrade_desc = check_contract_upgrades()

        print("\n[AI] OpenAI diagnosis...")
        risk_level, diagnosis = get_ai_diagnosis(
            tvl_status, tvl_change,
            admin_status, admin_desc,
            liquidity_status, liq_change,
            tx_status, upgrade_status
        )

        icons = {"HEALTHY": "[OK]", "WARNING": "[!!]", "CRITICAL": "[!!!]", "EMERGENCY": "[SOS]"}
        print(f"\n{'='*60}")
        print(f"  {icons.get(risk_level,'[??]')} OVERALL RISK: {risk_level}")
        print(f"  TVL: {current_tvl // 10**18} VLT | {tvl_status}")
        print(f"  Admin: {admin_status} | Liquidity: {current_liq // 10**18} VLT | {liquidity_status}")
        print(f"  TX: {tx_status} | Upgrades: {upgrade_status}")
        print(f"{'='*60}")

        # Evacuate whenever TVL drops critically AND funds are still in the protocol.
        # Don't wait for AI to say "EMERGENCY" — a critical TVL drop means act NOW.
        live_tvl = mock_protocol.functions.getTVL().call()
        if tvl_status == "CRITICAL" and live_tvl > 0:
            print(f"\n  *** TVL CRITICAL — {live_tvl // 10**18} VLT at risk — EVACUATING NOW ***")
            evacuate_funds()
        elif risk_level == "EMERGENCY" and live_tvl > 0:
            print(f"\n  *** EMERGENCY CONFIRMED — EVACUATING NOW ***")
            evacuate_funds()

        print(f"\n  Next check in {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    run_agent()
