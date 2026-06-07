import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

MONAD_RPC_URL         = os.getenv("MONAD_RPC_URL", "https://testnet-rpc.monad.xyz")
AGENT_PRIVATE_KEY     = os.getenv("AGENT_PRIVATE_KEY")
OPENAI_API_KEY        = os.getenv("OPENAI_API_KEY")
MOCK_PROTOCOL_ADDRESS = os.getenv("MOCK_PROTOCOL_ADDRESS")
MOCK_TOKEN_ADDRESS    = os.getenv("MOCK_TOKEN_ADDRESS")
BACKUP_WALLET         = os.getenv("BACKUP_WALLET")

CHECK_INTERVAL              = 30   # seconds between checks (demo mode)
TVL_WARNING_THRESHOLD       = 10   # % drop → WARNING
TVL_CRITICAL_THRESHOLD      = 30   # % drop → CRITICAL
LIQUIDITY_WARNING_THRESHOLD = 10
LIQUIDITY_CRITICAL_THRESHOLD= 25
TX_WARNING_MULTIPLIER       = 2    # 2x normal → WARNING
TX_CRITICAL_MULTIPLIER      = 5    # 5x normal → CRITICAL
