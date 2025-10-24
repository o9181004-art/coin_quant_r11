"""
UI Protection and Diagnostics

This module provides additional protection and diagnostics for the UI system
to prevent unintended service mutations and provide detailed logging.
"""

import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class UIProtection:
    """UI protection and diagnostics system"""
    
    def __init__(self, log_path: str = "logs/ui_protection.log"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(exist_ok=True)
        
        # Setup logging
        self.logger = logging.getLogger('ui_protection')
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.FileHandler(self.log_path)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        # Track UI actions
        self.ui_actions = []
        self.restart_history = []
        
        # Protection settings
        self.ui_allow_mutation = os.getenv('UI_ALLOW_SERVICE_MUTATION', 'false').lower() == 'true'
        self.max_ui_actions_per_minute = 10
        
    def log_ui_action(self, action: str, args: Dict[str, Any] = None, 
                     origin: str = 'ui', success: bool = True, error: str = None):
        """Log UI action for audit trail"""
        if args is None:
            args = {}
            
        action_record = {
            'timestamp': time.time(),
            'action': action,
            'args': args,
            'origin': origin,
            'success': success,
            'error': error,
            'ui_mutation_allowed': self.ui_allow_mutation
        }
        
        self.ui_actions.append(action_record)
        
        # Log to file
        if success:
            self.logger.info(f"UI Action: {action} from {origin} - Success")
        else:
            self.logger.error(f"UI Action: {action} from {origin} - Failed: {error}")
        
        # Keep only last 1000 actions
        if len(self.ui_actions) > 1000:
            self.ui_actions = self.ui_actions[-1000:]
    
    def log_restart_event(self, service: str, reason: str, spec_hash: str = '', 
                         ui_triggered: bool = False):
        """Log service restart event"""
        restart_record = {
            'timestamp': time.time(),
            'service': service,
            'reason': reason,
            'spec_hash': spec_hash,
            'ui_triggered': ui_triggered,
            'ui_mutation_allowed': self.ui_allow_mutation
        }
        
        self.restart_history.append(restart_record)
        
        # Log to file
        self.logger.info(
            f"Service Restart: {service} - Reason: {reason} - "
            f"UI Triggered: {ui_triggered} - Spec Hash: {spec_hash}"
        )
        
        # Keep only last 500 restarts
        if len(self.restart_history) > 500:
            self.restart_history = self.restart_history[-500:]
    
    def check_restart_frequency(self, service: str, window_minutes: int = 15) -> bool:
        """Check if service has been restarted too frequently"""
        cutoff_time = time.time() - (window_minutes * 60)
        
        recent_restarts = [
            r for r in self.restart_history
            if r['service'] == service and r['timestamp'] > cutoff_time
        ]
        
        max_restarts = 3 if service == 'trader' else 5
        
        if len(recent_restarts) >= max_restarts:
            self.logger.warning(
                f"High restart frequency detected for {service}: "
                f"{len(recent_restarts)} restarts in {window_minutes} minutes"
            )
            return True
        
        return False
    
    def detect_ui_refresh_restarts(self) -> Dict[str, Any]:
        """Detect if restarts were triggered by UI refreshes"""
        ui_refresh_restarts = []
        recent_window = time.time() - 3600  # Last hour
        
        for restart in self.restart_history:
            if restart['timestamp'] > recent_window and restart['ui_triggered']:
                # Check if there were UI actions around the same time
                action_window = restart['timestamp'] + 5  # 5 seconds after restart
                
                related_actions = [
                    a for a in self.ui_actions
                    if abs(a['timestamp'] - restart['timestamp']) < 5
                ]
                
                if not related_actions:  # No explicit UI action
                    ui_refresh_restarts.append({
                        'restart': restart,
                        'suspected_cause': 'UI_REFRESH'
                    })
        
        return {
            'total_restarts': len([r for r in self.restart_history if r['timestamp'] > recent_window]),
            'ui_triggered_restarts': len([r for r in self.restart_history if r['timestamp'] > recent_window and r['ui_triggered']]),
            'suspected_ui_refresh_restarts': len(ui_refresh_restarts),
            'details': ui_refresh_restarts
        }
    
    def get_protection_status(self) -> Dict[str, Any]:
        """Get comprehensive protection status"""
        recent_actions = [
            a for a in self.ui_actions
            if a['timestamp'] > time.time() - 3600  # Last hour
        ]
        
        recent_restarts = [
            r for r in self.restart_history
            if r['timestamp'] > time.time() - 3600  # Last hour
        ]
        
        ui_refresh_analysis = self.detect_ui_refresh_restarts()
        
        return {
            'ui_mutation_allowed': self.ui_allow_mutation,
            'recent_ui_actions': len(recent_actions),
            'recent_restarts': len(recent_restarts),
            'ui_refresh_analysis': ui_refresh_analysis,
            'protection_active': not self.ui_allow_mutation,
            'last_updated': time.time()
        }
    
    def generate_health_report(self) -> Dict[str, Any]:
        """Generate comprehensive health report"""
        now = time.time()
        
        # Service restart patterns
        restart_patterns = {}
        for service in ['trader', 'feeder', 'ares']:
            service_restarts = [r for r in self.restart_history if r['service'] == service]
            
            if service_restarts:
                last_restart = max(service_restarts, key=lambda x: x['timestamp'])
                restart_patterns[service] = {
                    'total_restarts': len(service_restarts),
                    'last_restart': last_restart['timestamp'],
                    'last_restart_age_seconds': now - last_restart['timestamp'],
                    'last_restart_reason': last_restart['reason'],
                    'ui_triggered_last': last_restart['ui_triggered']
                }
            else:
                restart_patterns[service] = {
                    'total_restarts': 0,
                    'last_restart': None,
                    'last_restart_age_seconds': None,
                    'last_restart_reason': None,
                    'ui_triggered_last': None
                }
        
        # UI action patterns
        ui_action_patterns = {}
        for action in ['start_trader', 'stop_trader', 'restart_trader', 'apply_ssot']:
            action_instances = [a for a in self.ui_actions if a['action'] == action]
            
            if action_instances:
                last_action = max(action_instances, key=lambda x: x['timestamp'])
                ui_action_patterns[action] = {
                    'total_actions': len(action_instances),
                    'last_action': last_action['timestamp'],
                    'last_action_age_seconds': now - last_action['timestamp'],
                    'last_action_success': last_action['success']
                }
            else:
                ui_action_patterns[action] = {
                    'total_actions': 0,
                    'last_action': None,
                    'last_action_age_seconds': None,
                    'last_action_success': None
                }
        
        return {
            'timestamp': now,
            'protection_status': self.get_protection_status(),
            'restart_patterns': restart_patterns,
            'ui_action_patterns': ui_action_patterns,
            'recommendations': self._generate_recommendations(restart_patterns, ui_action_patterns)
        }
    
    def _generate_recommendations(self, restart_patterns: Dict, ui_action_patterns: Dict) -> List[str]:
        """Generate recommendations based on patterns"""
        recommendations = []
        
        # Check for excessive restarts
        for service, pattern in restart_patterns.items():
            if pattern['total_restarts'] > 10:  # More than 10 restarts total
                recommendations.append(f"{service.title()} has been restarted {pattern['total_restarts']} times. Consider investigating stability issues.")
            
            if pattern['ui_triggered_last'] and pattern['last_restart_age_seconds'] < 300:  # UI triggered restart within 5 minutes
                recommendations.append(f"Recent {service} restart was UI-triggered. Ensure UI_ALLOW_SERVICE_MUTATION=false for production.")
        
        # Check UI action patterns
        for action, pattern in ui_action_patterns.items():
            if pattern['total_actions'] > 20:  # More than 20 actions total
                recommendations.append(f"High frequency of {action} actions. Consider using scheduled restarts instead.")
        
        # General recommendations
        if not self.ui_allow_mutation:
            recommendations.append("UI mutation protection is active. This is recommended for production environments.")
        else:
            recommendations.append("UI mutation is allowed. Consider setting UI_ALLOW_SERVICE_MUTATION=false for production safety.")
        
        return recommendations


# Global UI protection instance
_ui_protection = None

def get_ui_protection() -> UIProtection:
    """Get global UI protection instance"""
    global _ui_protection
    if _ui_protection is None:
        _ui_protection = UIProtection()
    return _ui_protection


def log_ui_action(action: str, args: Dict[str, Any] = None, origin: str = 'ui', 
                 success: bool = True, error: str = None):
    """Convenience function to log UI actions"""
    protection = get_ui_protection()
    protection.log_ui_action(action, args, origin, success, error)


def log_restart_event(service: str, reason: str, spec_hash: str = '', ui_triggered: bool = False):
    """Convenience function to log restart events"""
    protection = get_ui_protection()
    protection.log_restart_event(service, reason, spec_hash, ui_triggered)
