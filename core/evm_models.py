"""
Pydantic models for EVM tracking events.
Handles Ethereum token transfers, contract deployments, and address activity.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class EVMEventType(str, Enum):
    """Types of EVM events to track."""
    TOKEN_TRANSFER = "token_transfer"
    DEPLOYER_TX = "deployer_tx"
    TREASURY_TX = "treasury_tx"
    CONTRACT_DEPLOYMENT = "contract_deployment"


class AddressType(str, Enum):
    """Type of address being tracked."""
    TOKEN_CONTRACT = "token"
    TREASURY = "treasury"
    DEPLOYER = "deployer"
    CUSTOM = "custom"


class TrackedAddress(BaseModel):
    """Address being tracked on EVM chains."""
    id: Optional[int] = None
    user_id: int
    address: str  # Checksummed Ethereum address
    label: str  # Human-readable label (e.g., "LIT Treasury", "LIT Deployer")
    address_type: AddressType

    # Associated token contract (if tracking treasury/deployer for a specific token)
    token_contract: Optional[str] = None
    token_symbol: Optional[str] = None

    # Filtering settings
    min_value_usd: float = 0.0

    active: bool = True
    created_at: Optional[datetime] = None


class EVMTransferEvent(BaseModel):
    """ERC-20 token transfer event from Alchemy webhook."""
    token_address: str
    token_symbol: Optional[str] = None
    from_address: str
    to_address: str

    # Amount in hex string (raw value from blockchain)
    raw_value: str
    # Human-readable amount (converted using decimals)
    formatted_value: Optional[float] = None
    decimals: int = 18

    # USD value (optional, requires price API)
    value_usd: Optional[float] = None

    # Transaction details
    tx_hash: str
    block_number: int
    timestamp: datetime

    # Gas information
    gas_price_gwei: Optional[float] = None


class EVMTransactionEvent(BaseModel):
    """Generic transaction event for deployer/treasury tracking."""
    from_address: str
    to_address: Optional[str]  # None for contract creation

    # ETH value transferred
    value_wei: str
    value_eth: Optional[float] = None
    value_usd: Optional[float] = None

    # Transaction details
    tx_hash: str
    block_number: int
    timestamp: datetime

    # Gas information
    gas_price_gwei: float
    gas_used: Optional[int] = None

    # Transaction type detection
    is_contract_creation: bool = False
    method_signature: Optional[str] = None  # e.g., "0xa9059cbb" for transfer()


class EVMNotificationFilters(BaseModel):
    """User-level filters for EVM notifications."""
    enabled: bool = True
    min_transfer_value_usd: float = 0.0
    notify_on: List[EVMEventType] = Field(default_factory=lambda: list(EVMEventType))
    blacklist_addresses: List[str] = Field(default_factory=list)
