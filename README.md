# Protocol Vital Signs Agent

An AI agent that monitors a DeFi protocol's health on **Monad Testnet** and automatically saves user funds when an attack is detected.

Built for **Monad Blitz Bangalore V4** — June 7, 2026

---

## The Idea

DeFi rug pulls always have warning signs — TVL drops, admin draining funds, liquidity disappearing. But no one is watching 24/7. This agent watches every 30 seconds, asks AI to diagnose the risk, and **autonomously moves remaining user funds to a safe wallet** before the attacker can drain everything.

---

## How It Works

```
1. Agent reads 5 vital signs from MockProtocol (on Monad)
2. Sends them to OpenAI GPT-4o-mini for risk diagnosis
3. If TVL drops critically → agent calls agentDrainAll() on-chain
4. All remaining tokens move to a safe Backup Wallet instantly
5. MockProtocol = 0. User funds = saved.
```

---

## The 5 Vital Signs

| Vital Sign | What It Checks |
|---|---|
| TVL | Did total deposits drop suddenly? (>30% = CRITICAL) |
| Admin Wallet | Is the owner transferring funds to unknown addresses? |
| Liquidity Pool | Is liquidity being quietly removed? (>25% = CRITICAL) |
| TX Pattern | Unusual spike in transactions? (5x normal = CRITICAL) |
| Contract Upgrades | Did the contract owner change? |

---

## How It's On-Chain

- **Smart contracts** live permanently on Monad Testnet at fixed addresses
- Agent **reads** data via `eth_call` — free, no gas
- Agent **writes** data (evacuation) by signing a real transaction with its private key and broadcasting it to Monad
- Token movement is enforced by the EVM — not by Python code
- Every evacuation has a TX hash on [testnet.monadexplorer.com](https://testnet.monadexplorer.com)

---

## Deployed Contracts (Monad Testnet)

| Contract | Address |
|---|---|
| MockToken (VLT) | `0x4257A1306dfE3AA91367075B29e22950F459095e` |
| MockProtocol | `0x79C8c7960865455064170227d419b7d7B92362E8` |

---

## Tech Stack

- **Blockchain:** Monad Testnet (Chain ID: 10143)
- **Smart Contracts:** Solidity + Foundry
- **AI Agent:** Python + web3.py
- **AI Diagnosis:** OpenAI GPT-4o-mini
- **Dashboard:** Python http.server (port 3333)
- **Libraries:** OpenZeppelin ERC20

---

## Quick Start

### 1. Install dependencies
```bash
# Foundry
curl -L https://foundry.paradigm.xyz | bash && foundryup

# Python
pip install -r agent/requirements.txt
```

### 2. Setup `.env`
```bash
cp .env.example .env
# Fill in PRIVATE_KEY, AGENT_PRIVATE_KEY, OPENAI_API_KEY, BACKUP_WALLET
```

### 3. Build & test contracts
```bash
forge build
forge test -vvv
```

### 4. Deploy
```bash
forge script script/Deploy.s.sol --rpc-url https://testnet-rpc.monad.xyz --broadcast
# Copy printed addresses into .env
```

### 5. Setup demo & run
```bash
python3 agent/setup_demo.py   # deposit user funds
python3 agent/demo_server.py  # open http://localhost:3333
```

From the dashboard: **Start Agent** → **Run Attack** → watch evacuation trigger automatically.

---

## Demo Flow

```
Start:    MockProtocol = 2000 VLT (user deposits)
Attack:   Admin drains 40% → MockProtocol = 1200 VLT
Agent:    Detects TVL CRITICAL → calls agentDrainAll()
Result:   MockProtocol = 0 VLT | Backup Wallet = 1200 VLT (safe)
```

The attacker stole 40%. The agent saved the remaining 60%.

---

## Project Structure

```
protocol-vital-signs/
├── src/            Solidity smart contracts
├── test/           Foundry tests (9 tests)
├── script/         Deployment script
├── agent/          Python agent + dashboard + attack script
├── frontend/       Static HTML dashboard (Vercel)
└── foundry.toml    Foundry config
```

---

## Monad Testnet Config

```
RPC URL:   https://testnet-rpc.monad.xyz
Chain ID:  10143
Explorer:  https://testnet.monadexplorer.com
```

---

Built by **Jaswanth Chemarthipalli** | Monad Blitz Bangalore V4
