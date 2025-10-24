"""
WebSocket Connection Manager with Exponential Backoff and Circuit Breaker
"""
import asyncio
import random
import time
from typing import Dict
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit breaker open, no connections allowed
    HALF_OPEN = "half_open"  # Testing if service is back


class ConnectionBackoff:
    """Exponential backoff with jitter for WebSocket connections"""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, factor: float = 2.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.factor = factor
        self.attempts = 0
        self.last_attempt_time = 0
        
    def get_delay(self) -> float:
        """Calculate next delay with exponential backoff and jitter"""
        if self.attempts == 0:
            return 0
        
        # Exponential backoff
        delay = min(self.base_delay * (self.factor ** (self.attempts - 1)), self.max_delay)
        
        # Add jitter (0-500ms)
        jitter = random.uniform(0, 0.5)
        
        return delay + jitter
    
    def record_attempt(self):
        """Record a connection attempt"""
        self.attempts += 1
        self.last_attempt_time = time.time()
    
    def record_success(self):
        """Record successful connection - reset backoff"""
        self.attempts = 0
        self.last_attempt_time = 0
    
    def can_retry(self) -> bool:
        """Check if enough time has passed for next retry"""
        if self.attempts == 0:
            return True
        
        delay = self.get_delay()
        return time.time() - self.last_attempt_time >= delay


class CircuitBreaker:
    """Circuit breaker for WebSocket connections"""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 120.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = CircuitState.CLOSED
        
    def record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            print("[CIRCUIT_BREAKER] OPEN: {} consecutive failures".format(self.failure_count))
    
    def can_attempt(self) -> bool:
        """Check if connection attempt is allowed"""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if time.time() - self.last_failure_time >= self.timeout:
                self.state = CircuitState.HALF_OPEN
                print(f"[CIRCUIT_BREAKER] HALF_OPEN: Testing connection")
                return True
            return False
        
        if self.state == CircuitState.HALF_OPEN:
            return True
        
        return False
    
    def get_state(self) -> CircuitState:
        """Get current circuit breaker state"""
        return self.state


class WebSocketConnectionManager:
    """Manages WebSocket connections with backoff and circuit breaker"""
    
    def __init__(self):
        self.backoffs: Dict[str, ConnectionBackoff] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.connection_states: Dict[str, str] = {}  # IDLE, CONNECTING, CONNECTED, FAILED
        self.init_lock = asyncio.Lock()
        
    def _get_backoff(self, symbol: str) -> ConnectionBackoff:
        """Get or create backoff for symbol"""
        if symbol not in self.backoffs:
            self.backoffs[symbol] = ConnectionBackoff()
        return self.backoffs[symbol]
    
    def _get_circuit_breaker(self, symbol: str) -> CircuitBreaker:
        """Get or create circuit breaker for symbol"""
        if symbol not in self.circuit_breakers:
            self.circuit_breakers[symbol] = CircuitBreaker()
        return self.circuit_breakers[symbol]
    
    async def can_connect(self, symbol: str) -> tuple[bool, str]:
        """Check if connection is allowed for symbol"""
        backoff = self._get_backoff(symbol)
        circuit_breaker = self._get_circuit_breaker(symbol)
        
        # Check circuit breaker
        if not circuit_breaker.can_attempt():
            return False, f"CIRCUIT_OPEN: {circuit_breaker.get_state().value}"
        
        # Check backoff delay
        if not backoff.can_retry():
            delay = backoff.get_delay()
            return False, f"BACKOFF_DELAY: {delay:.1f}s remaining"
        
        # Check if already connecting
        if self.connection_states.get(symbol) == "CONNECTING":
            return False, "ALREADY_CONNECTING"
        
        return True, "OK"
    
    async def record_connection_attempt(self, symbol: str):
        """Record connection attempt"""
        backoff = self._get_backoff(symbol)
        backoff.record_attempt()
        self.connection_states[symbol] = "CONNECTING"
    
    async def record_connection_success(self, symbol: str):
        """Record successful connection"""
        backoff = self._get_backoff(symbol)
        circuit_breaker = self._get_circuit_breaker(symbol)
        
        backoff.record_success()
        circuit_breaker.record_success()
        self.connection_states[symbol] = "CONNECTED"
    
    async def record_connection_failure(self, symbol: str):
        """Record failed connection"""
        circuit_breaker = self._get_circuit_breaker(symbol)
        circuit_breaker.record_failure()
        self.connection_states[symbol] = "FAILED"
    
    async def get_connection_delay(self, symbol: str) -> float:
        """Get delay before next connection attempt"""
        backoff = self._get_backoff(symbol)
        return backoff.get_delay()
    
    def get_status(self, symbol: str) -> dict:
        """Get connection status for symbol"""
        backoff = self._get_backoff(symbol)
        circuit_breaker = self._get_circuit_breaker(symbol)
        
        return {
            "state": self.connection_states.get(symbol, "IDLE"),
            "circuit_state": circuit_breaker.get_state().value,
            "failure_count": circuit_breaker.failure_count,
            "backoff_attempts": backoff.attempts,
            "next_delay": backoff.get_delay()
        }


# Global instance
_connection_manager = None

def get_connection_manager() -> WebSocketConnectionManager:
    """Get singleton connection manager"""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = WebSocketConnectionManager()
    return _connection_manager
