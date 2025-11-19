"""
Auth Service - Gerenciamento de Login e Contexto
"""
import logging
import streamlit as st
from services.database import get_database_service

logger = logging.getLogger(__name__)
db = get_database_service()

class AuthService:
    def login(self, email, password):
        try:
            # 1. Autenticação Básica
            res = db.client.auth.sign_in_with_password({"email": email, "password": password})
            user = res.user
            
            if user:
                # 2. Buscar Contexto da Organização
                # Pega a primeira organização vinculada ao usuário
                member_res = db.client.table('organization_members')\
                    .select('role, organization_id, organizations(name)')\
                    .eq('user_id', user.id)\
                    .limit(1)\
                    .execute()
                
                # Valores padrão (caso não tenha vinculo ainda)
                user_role = 'member'
                org_id = None
                org_name = "Sem Organização"
                
                if member_res.data:
                    data = member_res.data[0]
                    user_role = data['role']
                    org_id = data['organization_id']
                    org_name = data['organizations']['name'] # Join automático do Supabase
                
                # 3. Salvar na Sessão
                st.session_state['user'] = user
                st.session_state['user_role'] = user_role
                st.session_state['user_org_id'] = org_id
                st.session_state['org_name'] = org_name
                
                return user
            return None
        except Exception as e:
            logger.warning(f"Login failed: {e}")
            return None

    def logout(self):
        db.client.auth.sign_out()
        st.session_state.clear()

    def is_logged_in(self):
        return 'user' in st.session_state