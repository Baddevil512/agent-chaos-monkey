"""
Custom exceptions raised during chaos injection testing.
"""

class ChaosEngineException(Exception):
    """Base exception for all agent chaos monkey faults."""
    pass


class ChaosHTTPError(ChaosEngineException):
    """Simulates HTTP status code failures (e.g. 502 Bad Gateway, 503 Service Unavailable, 429 Rate Limit)."""
    def __init__(self, status_code: int, message: str = None):
        self.status_code = status_code
        default_messages = {
            502: "502 Bad Gateway: Upstream agent service returned an invalid response.",
            503: "503 Service Unavailable: Upstream tool service is temporarily overloaded.",
            429: "429 Too Many Requests: Rate limit exceeded for tool API provider."
        }
        self.message = message or default_messages.get(status_code, f"HTTP {status_code} Error")
        super().__init__(f"[Chaos Injected] HTTP {self.status_code}: {self.message}")


class ChaosCorruptedJSONError(ChaosEngineException):
    """Simulates truncated or malformed JSON payloads returned by tool APIs."""
    def __init__(self, message: str = "JSONDecodeError: Unterminated string starting at line 1 column 42 (char 41)"):
        self.message = message
        super().__init__(f"[Chaos Injected] Corrupted JSON: {self.message}")


class ChaosEmptyResponseError(ChaosEngineException):
    """Simulates unexpected empty responses (0-byte payload or None) from tool APIs."""
    def __init__(self, message: str = "Upstream service returned empty string response"):
        self.message = message
        super().__init__(f"[Chaos Injected] Empty Response: {self.message}")


class ChaosLatencyTimeout(ChaosEngineException):
    """Simulates severe network delay causing downstream timeout."""
    def __init__(self, delay_sec: float):
        self.delay_sec = delay_sec
        super().__init__(f"[Chaos Injected] Latency Timeout: Injected delay of {delay_sec:.2f}s exceeded threshold")
