"""
Health State Hysteresis - Prevent rapid GREEN↔RED flapping

Once GREEN: stay GREEN unless K consecutive failures OR RED ≥ T seconds
Once RED: stay RED until genuine recovery
"""

import time
import logging

logger = logging.getLogger(__name__)


class HealthHysteresis:
    """
    Health state with hysteresis to prevent flapping
    
    Rules:
    - Once GREEN: stay GREEN unless K consecutive failures OR RED for T seconds
    - Once RED: stay RED until K consecutive successes
    - State changes are logged
    """
    
    def __init__(self, k_failures: int = 3, t_red_sec: int = 30, service_name: str = "service"):
        """
        Initialize hysteresis
        
        Args:
            k_failures: Number of consecutive failures to trigger RED
            t_red_sec: Seconds in RED state before triggering
            service_name: Name for logging
        """
        self.k_failures = k_failures
        self.t_red_sec = t_red_sec
        self.service_name = service_name
        
        self.state = "yellow"  # yellow | green | red
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.red_start_time = None
    
    def update(self, is_healthy: bool, metrics: dict = None) -> str:
        """
        Update state based on health check
        
        Args:
            is_healthy: Current probe result
            metrics: Dict of measured values for diagnostics
        
        Returns:
            Current state (green/yellow/red)
        """
        if is_healthy:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.red_start_time = None
            
            # Recover to GREEN after 2 consecutive successes
            if self.state != "green" and self.consecutive_successes >= 2:
                logger.info(
                    f"🟢 {self.service_name} health recovered: {self.state} → GREEN"
                )
                self.state = "green"
        
        else:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            
            # Mark RED start time on first failure
            if self.red_start_time is None:
                self.red_start_time = time.time()
            
            red_duration = time.time() - self.red_start_time
            
            # Transition to RED if:
            # 1. K consecutive failures, OR
            # 2. RED for T seconds
            if self.consecutive_failures >= self.k_failures:
                if self.state != "red":
                    logger.warning(
                        f"🔴 {self.service_name} health degraded: "
                        f"{self.consecutive_failures} consecutive failures "
                        f"(threshold: {self.k_failures})"
                    )
                    self.state = "red"
            
            elif red_duration >= self.t_red_sec:
                if self.state != "red":
                    logger.warning(
                        f"🔴 {self.service_name} health degraded: "
                        f"RED for {red_duration:.1f}s (threshold: {self.t_red_sec}s)"
                    )
                    self.state = "red"
            
            # Hysteresis: stay GREEN despite failures (until thresholds met)
            elif self.state == "green":
                logger.debug(
                    f"[hysteresis] {self.service_name} GREEN maintained despite failure "
                    f"(failures: {self.consecutive_failures}/{self.k_failures}, "
                    f"duration: {red_duration:.1f}s/{self.t_red_sec}s)"
                )
        
        return self.state
    
    def why_not_green(self, metrics: dict = None) -> str:
        """
        Explain why not GREEN with actual⇒threshold pairs
        
        Args:
            metrics: Dict of {key: {"actual": val, "threshold": val}}
        
        Returns:
            WhyNotGREEN string (empty if GREEN)
        """
        if self.state == "green":
            return ""  # Empty when GREEN
        
        reasons = []
        
        if self.consecutive_failures > 0:
            reasons.append(
                f"consecutive_failures={self.consecutive_failures}⇒{self.k_failures}"
            )
        
        if self.red_start_time:
            duration = time.time() - self.red_start_time
            reasons.append(
                f"red_duration={duration:.1f}s⇒{self.t_red_sec}s"
            )
        
        # Add metrics if provided
        if metrics:
            for key, val in metrics.items():
                if isinstance(val, dict) and 'actual' in val and 'threshold' in val:
                    reasons.append(
                        f"{key}={val['actual']}⇒{val['threshold']}"
                    )
        
        return f"WhyNotGREEN: {'; '.join(reasons)}"
    
    def get_state(self) -> str:
        """Get current state"""
        return self.state
    
    def reset(self):
        """Reset to initial state"""
        self.state = "yellow"
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.red_start_time = None

