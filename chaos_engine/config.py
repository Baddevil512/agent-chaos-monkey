"""
Configuration definitions and global profiles for Agent Chaos Monkey.
"""

from enum import Enum
from typing import List, Tuple, Optional
from dataclasses import dataclass, field


class FaultType(str, Enum):
    LATENCY = "network_latency"
    HTTP_502 = "http_502"
    HTTP_503 = "http_503"
    HTTP_429 = "http_429"
    CORRUPTED_JSON = "corrupted_json"
    EMPTY_RESPONSE = "empty_response"


@dataclass
class ChaosConfig:
    """Configuration options for chaos fault injection."""
    enabled: bool = True
    rate: float = 0.5  # Fault injection probability (0.0 to 1.0)
    fault_types: List[FaultType] = field(default_factory=lambda: [
        FaultType.LATENCY,
        FaultType.HTTP_502,
        FaultType.HTTP_503,
        FaultType.HTTP_429,
        FaultType.CORRUPTED_JSON,
        FaultType.EMPTY_RESPONSE
    ])
    latency_range: Tuple[float, float] = (0.5, 2.5)  # Injected sleep range in seconds
    raise_exceptions: bool = True  # If False, returns corrupted payload instead of raising exception for JSON/empty
    
    # Financial token estimation settings ($ per 1K tokens)
    token_cost_prompt: float = 0.0025    # Standard input token cost ($2.50 per 1M)
    token_cost_completion: float = 0.010 # Standard output token cost ($10.00 per 1M)
    monthly_call_volume_multiplier: float = 10000.0  # Estimated monthly call multiplier for leak calculation


# Global default configuration instance
_GLOBAL_CONFIG = ChaosConfig()


def get_global_config() -> ChaosConfig:
    return _GLOBAL_CONFIG


def set_global_config(config: ChaosConfig):
    global _GLOBAL_CONFIG
    _GLOBAL_CONFIG = config
