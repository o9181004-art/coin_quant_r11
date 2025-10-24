#!/usr/bin/env python3
"""
거래 내역장 페이지 - Streamlit pages integration
"""
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import and run the trades ledger
try:
    from guard.ui.trades_ledger import main
    
    if __name__ == "__main__":
        main()
        
except ImportError as e:
    import streamlit as st
    st.error(f"거래 내역장을 불러올 수 없습니다: {e}")
    st.info("필요한 모듈이 설치되지 않았거나 경로를 찾을 수 없습니다.")
except Exception as e:
    import streamlit as st
    st.error(f"거래 내역장 실행 중 오류가 발생했습니다: {e}")

