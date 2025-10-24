#!/usr/bin/env python3
"""
Environment Drift Panel - UI components for drift detection and reconciliation
"""

import streamlit as st
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional


def render_env_drift_status():
    """Render environment drift status in Health panel"""
    try:
        from shared.environment_manager import (
            get_drift_status, get_mode_status, get_masked_diff, 
            reconcile_to_runtime, reconcile_to_ssot, get_sources_info,
            get_ssot_path, self_test
        )
        
        # Check for hash calculation mismatch
        hash_consistent = _check_hash_consistency()
        
        # Show hash consistency status
        if not hash_consistent:
            st.error("❌ Hash calculation mismatch detected between Header and Health contexts")
        
        # Get drift status
        drift_status = get_drift_status()
        mode_status = get_mode_status()
        sources_info = get_sources_info()
        
        # Status indicator
        status_color = {
            'green': '🟢',
            'yellow': '🟡', 
            'red': '🔴'
        }.get(drift_status['status'], '⚪')
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"**env_drift** {status_color} {drift_status['message']}")
        
        with col2:
            st.text(f"Current: {drift_status['current_hash']}")
        
        with col3:
            st.text(f"SSOT: {drift_status['ssot_hash']}")
        
        # Action buttons if drift detected
        if drift_status['status'] != 'green':
            st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 2])
            
            with col1:
                if st.button("🔄 Use Runtime as SSOT", key="reconcile_runtime"):
                    with st.spinner("Reconciling to runtime..."):
                        success = reconcile_to_runtime()
                        if success:
                            ssot_path = get_ssot_path()
                            from shared.environment_manager import get_env_hash
                            new_hash = get_env_hash()
                            st.success(f"✅ Wrote SSOT → {ssot_path} (hash {new_hash})")
                            # Force hard refresh by clearing session state
                            _clear_env_cache()
                            st.rerun()
                        else:
                            st.error("❌ Reconciliation failed")
            
            with col2:
                if st.button("📥 Apply SSOT to Services", key="reconcile_ssot"):
                    with st.spinner("Reconciling to SSOT..."):
                        success = reconcile_to_ssot()
                        if success:
                            st.success("✅ Reconciled to SSOT")
                            st.info("💡 Services will restart with SSOT values")
                            # Force hard refresh by clearing session state
                            _clear_env_cache()
                            st.rerun()
                        else:
                            st.error("❌ Reconciliation failed")
            
            with col3:
                if st.button("👁️ View Diff", key="view_diff"):
                    st.session_state['show_env_diff'] = True
        
        # Mode indicator
        mode_color = mode_status['color']
        mode_text = mode_status['mode']
        lock_icon = "🔒" if mode_status['locked'] else ""
        
        st.caption(f"Mode: {mode_text} {lock_icon}")
        
        # Show diff modal if requested
        if st.session_state.get('show_env_diff', False):
            render_env_diff_modal()
        
        # Debug toggle
        if os.getenv('ENV_DEBUG', 'false').lower() in ('true', '1', 'yes'):
            render_debug_info()
            
    except ImportError as e:
        st.error(f"❌ Environment Manager not available: {e}")
    except Exception as e:
        st.error(f"❌ Environment drift check failed: {e}")


def _check_hash_consistency():
    """Check for hash calculation consistency between Header and Health contexts"""
    try:
        from shared.environment_manager import self_test, get_env_hash
        
        # Run self-test to verify consistency
        test_result = self_test()
        
        # Get hash from UI context (Header context)
        header_hash = get_env_hash()
        
        # Get hash from background context (Health context)
        background_hash = test_result['current_hash']
        
        # Check for mismatch
        if header_hash != background_hash:
            st.warning(f"⚠️ ENV_HASH_CALC_SOURCE_MISMATCH: Header={header_hash}, Health={background_hash}")
            return False
        
        return True
            
    except Exception as e:
        st.error(f"❌ Hash consistency check failed: {e}")
        return False


def _clear_env_cache():
    """Clear environment-related session state and cache"""
    try:
        import streamlit as st
        
        # Clear any cached environment data
        keys_to_clear = [
            'env_drift_status', 'env_mode_status', 'env_sources_info',
            'env_material_keys', 'env_hash', 'env_ssot_data', 'env_drift_age',
            'env_mode_indicator', 'env_debug_info', 'env_reconcile_status'
        ]
        
        for key in keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear Streamlit cache for environment data
        if hasattr(st, 'cache_data'):
            # Clear any cached environment-related data
            st.cache_data.clear()
            
    except ImportError:
        # Streamlit not available in non-UI context
        pass
    except Exception:
        # Other errors in cache clearing
        pass


def render_debug_info():
    """Render debug information when ENV_DEBUG=true"""
    try:
        from shared.environment_manager import get_drift_status, get_sources_info, get_ssot_path, self_test, get_env_hash
        
        st.markdown("---")
        st.markdown("### 🔧 Env Debug (ENV_DEBUG=true)")
        
        # Hash information
        drift_status = get_drift_status()
        current_hash = get_env_hash()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.text(f"Runtime Hash: {current_hash}")
            st.text(f"SSOT Hash: {drift_status['ssot_hash']}")
            st.text(f"Hash Match: {'✅' if current_hash == drift_status['ssot_hash'] else '❌'}")
        
        with col2:
            st.text(f"SSOT Path: {get_ssot_path().absolute()}")
            st.text(f"Drift Status: {drift_status['status']}")
            st.text(f"Severity: {drift_status.get('severity', 'unknown')}")
        
        # Sources information
        sources_info = get_sources_info()
        st.markdown("#### 📁 Environment Sources")
        st.text("Loaded sources (ordered):")
        for i, source in enumerate(sources_info.get('loaded_sources', []), 1):
            st.text(f"  {i}. {source}")
        
        # Material keys information
        test_result = self_test()
        st.markdown("#### 🔑 Material Keys")
        st.text(f"Material Keys: {len(test_result['material_keys'])} patterns")
        st.text(f"Excluded Volatile: {len(test_result['excluded_volatile_keys'])} keys")
        
        # Show material keys preview (non-secret)
        material_keys = test_result['material_keys']
        if material_keys:
            st.text("Material key patterns (preview):")
            for key in sorted(material_keys)[:10]:  # Show first 10
                st.text(f"  • {key}")
            if len(material_keys) > 10:
                st.text(f"  ... and {len(material_keys) - 10} more")
        
        # Show excluded volatile keys
        excluded_keys = test_result['excluded_volatile_keys']
        if excluded_keys:
            st.text("Excluded volatile keys:")
            for key in sorted(excluded_keys)[:5]:  # Show first 5
                st.text(f"  • {key}")
            if len(excluded_keys) > 5:
                st.text(f"  ... and {len(excluded_keys) - 5} more")
        
        # Mask secrets consistently
        st.markdown("#### 🔐 Environment Values (masked)")
        from shared.environment_manager import get_material_env
        material_env = get_material_env()
        
        for key, value in sorted(material_env.items()):
            if 'SECRET' in key.upper() or 'KEY' in key.upper() or 'PASSWORD' in key.upper():
                # Mask secrets: first 2 + last 2 chars
                if len(value) > 4:
                    masked_value = value[:2] + "*" * (len(value) - 4) + value[-2:]
                else:
                    masked_value = "*" * len(value)
                st.text(f"  {key}: {masked_value}")
            else:
                st.text(f"  {key}: {value}")
        
    except Exception as e:
        st.error(f"❌ Debug info failed: {e}")


def render_env_diff_modal():
    """Render environment diff modal"""
    try:
        from shared.environment_manager import get_masked_diff, get_sources_info
        
        diff_data = get_masked_diff()
        sources_info = get_sources_info()
        
        if not diff_data:
            st.info("No drift detected")
            st.session_state['show_env_diff'] = False
            return
        
        st.markdown("### 🔍 Environment Drift Details")
        
        # Severity indicator
        severity = diff_data.get('severity', 'unknown')
        severity_color = {
            'soft': '🟡',
            'hard': '🔴'
        }.get(severity, '⚪')
        
        st.markdown(f"**Severity:** {severity_color} {severity.upper()}")
        
        # Added variables
        if diff_data.get('added'):
            st.markdown("#### ➕ Added Variables")
            for key, value in diff_data['added'].items():
                st.text(f"  {key} = {value}")
        
        # Removed variables  
        if diff_data.get('removed'):
            st.markdown("#### ➖ Removed Variables")
            for key, value in diff_data['removed'].items():
                st.text(f"  {key} = {value}")
        
        # Changed variables
        if diff_data.get('changed'):
            st.markdown("#### 🔄 Changed Variables")
            for key, (old_value, new_value) in diff_data['changed'].items():
                st.text(f"  {key}: {old_value} → {new_value}")
        
        # Sources information
        st.markdown("#### 📁 Environment Sources")
        
        if sources_info.get('loaded_sources'):
            st.text("Loaded sources:")
            for source in sources_info['loaded_sources']:
                st.text(f"  • {source}")
        
        if sources_info.get('ssot_source'):
            ssot_time = sources_info.get('ssot_updated', 0)
            if ssot_time:
                ssot_dt = datetime.fromtimestamp(ssot_time, tz=timezone.utc)
                st.text(f"SSOT source: {sources_info['ssot_source']} (updated: {ssot_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC)")
            else:
                st.text(f"SSOT source: {sources_info['ssot_source']}")
        
        # SSOT path information
        if 'ssot_path' in sources_info:
            st.text(f"SSOT path: {sources_info['ssot_path']}")
        
        # Close button
        if st.button("❌ Close", key="close_diff"):
            st.session_state['show_env_diff'] = False
            st.rerun()
            
    except Exception as e:
        st.error(f"❌ Failed to show diff: {e}")


def render_mode_indicator():
    """Render trading mode indicator in header"""
    try:
        from shared.environment_manager import get_mode_status, get_drift_status, get_env_hash
        
        # Clear any cached data to ensure fresh values
        _clear_env_cache()
        
        mode_status = get_mode_status()
        drift_status = get_drift_status()
        current_hash = get_env_hash()
        
        mode_color = mode_status['color']
        mode_text = mode_status['mode']
        lock_icon = "🔒" if mode_status['locked'] else ""
        drift_icon = "⚠️" if drift_status['status'] != 'green' else ""
        
        # Mode badge with hash for debugging
        badge_color = {
            'red': '🔴',
            'blue': '🔵', 
            'gray': '⚪'
        }.get(mode_color, '⚪')
        
        # Show hash in debug mode
        hash_display = f" ({current_hash})" if os.getenv('ENV_DEBUG', 'false').lower() in ('true', '1', 'yes') else ""
        
        st.markdown(f"""
        <div style="display: inline-block; padding: 4px 8px; background-color: #1e1e1e; 
                    border-radius: 4px; margin: 0 8px;">
            {badge_color} {mode_text}{hash_display} {lock_icon} {drift_icon}
        </div>
        """, unsafe_allow_html=True)
        
    except ImportError:
        st.markdown("Mode: ❌")
    except Exception as e:
        st.markdown(f"Mode: ⚠️")


def render_env_sources_diagnostic():
    """Render environment sources diagnostic (collapsed by default)"""
    try:
        from shared.environment_manager import get_sources_info, get_ssot_path
        import pathlib
        
        sources_info = get_sources_info()
        
        with st.expander("🔧 View Paths", expanded=False):
            st.markdown("#### 📁 Path Information")
            
            # Current working directory
            st.text(f"cwd: {pathlib.Path.cwd()}")
            
            # Repository root
            try:
                from shared.path_registry import get_absolute_path
                repo_root = get_absolute_path('repo_root')
                st.text(f"repo_root: {repo_root}")
            except:
                st.text("repo_root: Not available")
            
            # SSOT path
            ssot_path = get_ssot_path()
            st.text(f"ssot_path: {ssot_path.absolute()}")
            
            st.markdown("#### 📁 Loaded Sources")
            
            if sources_info.get('loaded_sources'):
                for i, source in enumerate(sources_info['loaded_sources'], 1):
                    st.text(f"{i}. {source}")
            else:
                st.text("No sources loaded")
            
            st.markdown("#### 🏛️ SSOT Information")
            
            ssot_source = sources_info.get('ssot_source', 'none')
            ssot_updated = sources_info.get('ssot_updated', 0)
            
            st.text(f"Source: {ssot_source}")
            
            if ssot_updated:
                ssot_dt = datetime.fromtimestamp(ssot_updated, tz=timezone.utc)
                age_seconds = datetime.now(timezone.utc).timestamp() - ssot_updated
                st.text(f"Updated: {ssot_dt.strftime('%Y-%m-%d %H:%M:%S')} UTC ({age_seconds:.0f}s ago)")
            else:
                st.text("Updated: Never")
            
            # Environment hash info
            try:
                from shared.environment_manager import get_env_hash, get_ssot_hash
                st.markdown("#### 🔑 Hash Information")
                st.text(f"Current: {get_env_hash()}")
                st.text(f"SSOT: {get_ssot_hash()}")
            except:
                pass
                
    except Exception as e:
        st.error(f"❌ Failed to load environment sources: {e}")


def check_trading_block():
    """Check if trading should be blocked due to environment drift"""
    try:
        from shared.environment_manager import should_block_trading
        
        blocked, reason = should_block_trading()
        
        if blocked:
            st.error(f"🚫 Trading Blocked: {reason}")
            st.info("💡 Use the reconcile buttons above to fix environment drift")
            return True
        
        return False
        
    except Exception as e:
        st.warning(f"⚠️ Could not check trading block status: {e}")
        return False
