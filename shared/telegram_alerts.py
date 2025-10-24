#!/usr/bin/env python3
"""
Telegram Alerts
========================================
Send alerts to Telegram with mode prefix.

All alerts include [TESTNET] or [LIVE] prefix based on environment.
"""

import os
import time
from typing import Optional


def get_mode_prefix() -> str:
    """Get mode prefix for alerts"""
    testnet = os.getenv("BINANCE_USE_TESTNET", "true").lower() == "true"
    canary = os.getenv("CANARY_MODE", "false").lower() == "true"
    
    if testnet:
        return "[TESTNET]"
    elif canary:
        return "[CANARY]"
    else:
        return "[LIVE]"


def send_telegram_alert(message: str, priority: str = "INFO"):
    """
    Send Telegram alert with mode prefix.
    
    Args:
        message: Alert message
        priority: INFO, WARNING, CRITICAL
    
    Note:
        Requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment.
        If not configured, prints to console only.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    # Add mode prefix
    mode_prefix = get_mode_prefix()
    full_message = f"{mode_prefix} {priority}: {message}"
    
    if not bot_token or not chat_id:
        # No Telegram configured - print to console
        print(f"[TelegramAlert] {full_message}")
        return
    
    try:
        import requests
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": full_message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=payload, timeout=5)
        
        if response.status_code == 200:
            print(f"[TelegramAlert] Sent: {full_message}")
        else:
            print(f"[TelegramAlert] Failed to send: {response.status_code}")
    
    except Exception as e:
        print(f"[TelegramAlert] Error sending alert: {e}")
        print(f"[TelegramAlert] Message: {full_message}")


def alert_circuit_breaker_trip(symbol: str, reason: str):
    """Alert when circuit breaker trips"""
    message = f"🚨 Circuit Breaker TRIPPED for {symbol}: {reason}"
    send_telegram_alert(message, priority="CRITICAL")


def alert_stale_data(component: str, age_sec: float):
    """Alert when data becomes stale"""
    message = f"⚠️ Stale data detected: {component} age {age_sec:.1f}s"
    send_telegram_alert(message, priority="WARNING")


def alert_auto_heal_restart(service: str):
    """Alert when auto-heal restarts a service"""
    message = f"🔄 Auto-Heal restarted {service} service"
    send_telegram_alert(message, priority="WARNING")


def alert_trade_executed(symbol: str, side: str, qty: float, price: float):
    """Alert when trade is executed"""
    message = f"✅ Trade executed: {symbol} {side} {qty:.4f} @ ${price:,.2f}"
    send_telegram_alert(message, priority="INFO")


def alert_daily_loss_limit(current_loss: float, limit: float):
    """Alert when approaching or hitting daily loss limit"""
    message = f"🚨 Daily loss limit: ${current_loss:,.2f} / ${limit:,.2f}"
    send_telegram_alert(message, priority="CRITICAL")


if __name__ == "__main__":
    # Test alerts
    print("Testing Telegram alerts...")
    
    mode_prefix = get_mode_prefix()
    print(f"Mode prefix: {mode_prefix}")
    
    alert_circuit_breaker_trip("BTCUSDT", "3 consecutive failures")
    alert_stale_data("Feeder", 45.0)
    alert_auto_heal_restart("Trader")
    alert_trade_executed("BTCUSDT", "BUY", 0.001, 50000.0)

