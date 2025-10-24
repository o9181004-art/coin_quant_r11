#!/usr/bin/env python3
"""
Telegram Command Listener
Handles admin commands for risk mode management via file-based command queue
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from guard.risk.risk_mode_manager import get_risk_mode_manager
from shared.state.risk_mode_store import get_risk_mode_store


class TelegramCommandListener:
    """
    Telegram Command Listener

    Listens for commands via file-based queue and executes them.
    Commands are written to shared_data/commands/telegram_cmd.json

    Supported commands:
    - /status: Get risk mode status
    - /resume_aggressive: Resume AGGRESSIVE mode (if policy allows)
    - /set_mode SAFE|AGGRESSIVE: Set mode manually (admin override)
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Command queue path
        self.command_file = Path("shared_data/commands/telegram_cmd.json")
        self.command_file.parent.mkdir(parents=True, exist_ok=True)

        # Response path
        self.response_file = Path("shared_data/commands/telegram_response.json")

        # Managers
        self.risk_manager = get_risk_mode_manager()
        self.risk_store = get_risk_mode_store()

        # Last processed command timestamp
        self._last_processed_ts = 0.0

        self.logger.info("TelegramCommandListener initialized")

    def check_and_process_commands(self):
        """Check for new commands and process them"""
        try:
            if not self.command_file.exists():
                return

            # Read command
            with open(self.command_file, 'r', encoding='utf-8') as f:
                command_data = json.load(f)

            # Check if already processed
            cmd_ts = command_data.get("timestamp", 0)
            if cmd_ts <= self._last_processed_ts:
                return

            # Process command
            command = command_data.get("command", "")
            args = command_data.get("args", [])

            self.logger.info(f"Processing command: {command} {args}")

            response = self._execute_command(command, args)

            # Write response
            self._write_response(response)

            # Update last processed timestamp
            self._last_processed_ts = cmd_ts

            # Delete command file
            self.command_file.unlink()

        except Exception as e:
            self.logger.error(f"Failed to process command: {e}")

    def _execute_command(self, command: str, args: list) -> Dict[str, Any]:
        """Execute command and return response"""
        try:
            if command == "/status":
                return self._cmd_status()

            elif command == "/resume_aggressive":
                return self._cmd_resume_aggressive()

            elif command == "/set_mode":
                if len(args) < 1:
                    return {"success": False, "message": "Usage: /set_mode SAFE|AGGRESSIVE"}
                mode = args[0].upper()
                return self._cmd_set_mode(mode)

            else:
                return {"success": False, "message": f"Unknown command: {command}"}

        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    def _cmd_status(self) -> Dict[str, Any]:
        """Handle /status command"""
        try:
            status = self.risk_manager.get_status()

            # Format response
            message = (
                f"📊 Risk Mode Status\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Mode: {status['current_mode']}\n"
                f"Auto-Switch: {'✅' if status['auto_switch_enabled'] else '❌'}\n"
                f"Return Policy: {status['return_policy']}\n"
                f"\n"
                f"📈 Metrics\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Intraday PnL: {status['intraday_pnl_pct']:.2f}%\n"
                f"Consecutive Losses: {status['consecutive_losses']}\n"
                f"Day Open Equity: ${status['day_open_equity']:.2f}\n"
                f"\n"
                f"⚙️ Profile: {status['profile']['name']}\n"
                f"Daily Loss Limit: {status['profile']['daily_loss_limit_pct']}%\n"
                f"Max Positions: {status['profile']['max_concurrent_positions']}\n"
            )

            if status['last_switch_reason']:
                message += (
                    f"\n"
                    f"🔄 Last Switch\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Reason: {status['last_switch_reason']}\n"
                    f"Time: {status['last_switch_ts']}\n"
                )

            return {
                "success": True,
                "message": message,
                "data": status
            }

        except Exception as e:
            self.logger.error(f"Status command failed: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    def _cmd_resume_aggressive(self) -> Dict[str, Any]:
        """Handle /resume_aggressive command"""
        try:
            # Check if in SAFE mode
            if not self.risk_store.is_safe_mode():
                return {
                    "success": False,
                    "message": "Already in AGGRESSIVE mode"
                }

            # Check policy
            status = self.risk_manager.get_status()
            if status['return_policy'] != "MANUAL":
                return {
                    "success": False,
                    "message": f"Manual resume not allowed with {status['return_policy']} policy"
                }

            # Resume aggressive
            success = self.risk_manager.resume_aggressive(auto=False)

            if success:
                return {
                    "success": True,
                    "message": "✅ AGGRESSIVE mode resumed successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to resume AGGRESSIVE mode"
                }

        except Exception as e:
            self.logger.error(f"Resume aggressive command failed: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    def _cmd_set_mode(self, mode: str) -> Dict[str, Any]:
        """Handle /set_mode command (admin override)"""
        try:
            if mode not in ["SAFE", "AGGRESSIVE"]:
                return {
                    "success": False,
                    "message": "Invalid mode. Use SAFE or AGGRESSIVE"
                }

            # Get current mode
            current_mode = self.risk_store.get_mode()

            if current_mode == mode:
                return {
                    "success": False,
                    "message": f"Already in {mode} mode"
                }

            # Switch mode with manual override
            reason = f"manual_override_telegram"
            success = self.risk_store.switch_mode(mode, reason, manual_override=True)

            if success:
                # Apply profile
                if mode == "SAFE":
                    from guard.risk.risk_profiles import apply_profile_safe
                    apply_profile_safe()
                else:
                    from guard.risk.risk_profiles import apply_profile_aggressive
                    apply_profile_aggressive()

                # Log
                self.logger.warning(
                    f"⚠️ MANUAL OVERRIDE: Mode set to {mode} via Telegram command"
                )

                return {
                    "success": True,
                    "message": f"✅ Mode set to {mode} (manual override)"
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to set mode to {mode}"
                }

        except Exception as e:
            self.logger.error(f"Set mode command failed: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}

    def _write_response(self, response: Dict[str, Any]):
        """Write response to file"""
        try:
            response["timestamp"] = time.time()

            with open(self.response_file, 'w', encoding='utf-8') as f:
                json.dump(response, f, indent=2)

            self.logger.debug(f"Response written: {response.get('success')}")

        except Exception as e:
            self.logger.error(f"Failed to write response: {e}")


# Global instance
_global_telegram_listener: Optional[TelegramCommandListener] = None


def get_telegram_listener() -> TelegramCommandListener:
    """Get global Telegram command listener"""
    global _global_telegram_listener
    if _global_telegram_listener is None:
        _global_telegram_listener = TelegramCommandListener()
    return _global_telegram_listener


def check_telegram_commands():
    """Check and process Telegram commands (convenience function)"""
    get_telegram_listener().check_and_process_commands()
