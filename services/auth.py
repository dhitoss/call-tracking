"""
Auth Service - Gerenciamento de Login/Sessão via Supabase
"""
import logging
from services.database import get_database_service
import streamlit as st

logger = logging.getLogger(__name__)
db = get_database_service()

class AuthService:
    def login(self, email, password):
        """Tenta realizar login no Supabase Auth"""
        try:
            response = db.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user:
                logger.info(f"✅ User logged in: {response.user.email}")
                return response.user
            return None
            
        except Exception as e:
            logger.warning(f"❌ Login failed: {e}")
            return None

    def logout(self):
        """Desloga e limpa sessão"""
        try:
            db.client.auth.sign_out()
            # Limpa sessão do Streamlit
            for key in list(st.session_state.keys()):
                del st.session_state[key]
        except Exception as e:
            logger.error(f"Logout error: {e}")

    def is_logged_in(self):
        """Verifica se existe sessão ativa"""
        return 'user' in st.session_state and st.session_state['user'] is not None