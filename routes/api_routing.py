"""
Routes - API de Gerenciamento
Endpoints REST para gerenciar rotas, tracking e analytics
"""

from flask import request, jsonify
from typing import Dict, Any
import logging

from services.database import DatabaseService

logger = logging.getLogger(__name__)
db = DatabaseService()

# ============================================================================
# ROUTING - CRUD
# ============================================================================

def get_all_routes() -> tuple[Dict[str, Any], int]:
    """Lista todas as rotas configuradas."""
    try:
        is_active = request.args.get('is_active')
        campaign = request.args.get('campaign')
        
        query = db.client.table('phone_routing').select('*')
        
        if is_active is not None:
            query = query.eq('is_active', is_active.lower() == 'true')
        
        if campaign:
            query = query.eq('campaign', campaign)
        
        query = query.order('created_at', desc=True)
        result = query.execute()
        
        return jsonify({
            'success': True,
            'count': len(result.data),
            'routes': result.data
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error fetching routes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def create_route() -> tuple[Dict[str, Any], int]:
    """Cria nova rota de número."""
    try:
        data = request.get_json()
        
        required_fields = ['tracking_number', 'destination_number']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        for field in ['tracking_number', 'destination_number']:
            if not data[field].startswith('+'):
                return jsonify({
                    'success': False,
                    'error': f'{field} must start with +'
                }), 400
        
        route_data = {
            'tracking_number': data['tracking_number'],
            'destination_number': data['destination_number'],
            'campaign': data.get('campaign'),
            'is_active': data.get('is_active', True)
        }
        
        result = db.client.table('phone_routing').insert(route_data).execute()
        
        logger.info(f"✅ Route created: {data['tracking_number']} → {data['destination_number']}")
        
        return jsonify({
            'success': True,
            'route': result.data[0]
        }), 201
        
    except Exception as e:
        logger.error(f"❌ Error creating route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def get_route(route_id: str) -> tuple[Dict[str, Any], int]:
    """Busca rota específica por ID."""
    try:
        result = db.client.table('phone_routing').select('*').eq('id', route_id).execute()
        
        if not result.data:
            return jsonify({'success': False, 'error': 'Route not found'}), 404
        
        return jsonify({'success': True, 'route': result.data[0]}), 200
        
    except Exception as e:
        logger.error(f"❌ Error fetching route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def update_route(route_id: str) -> tuple[Dict[str, Any], int]:
    """Atualiza rota existente."""
    try:
        data = request.get_json()
        
        existing = db.client.table('phone_routing').select('*').eq('id', route_id).execute()
        
        if not existing.data:
            return jsonify({'success': False, 'error': 'Route not found'}), 404
        
        update_data = {}
        
        if 'destination_number' in data:
            if not data['destination_number'].startswith('+'):
                return jsonify({
                    'success': False,
                    'error': 'destination_number must start with +'
                }), 400
            update_data['destination_number'] = data['destination_number']
        
        if 'campaign' in data:
            update_data['campaign'] = data['campaign']
        
        if 'is_active' in data:
            update_data['is_active'] = data['is_active']
        
        if not update_data:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400
        
        result = db.client.table('phone_routing').update(update_data).eq('id', route_id).execute()
        
        logger.info(f"✅ Route updated: {route_id}")
        
        return jsonify({'success': True, 'route': result.data[0]}), 200
        
    except Exception as e:
        logger.error(f"❌ Error updating route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def delete_route(route_id: str) -> tuple[Dict[str, Any], int]:
    """Deleta rota (soft delete)."""
    try:
        existing = db.client.table('phone_routing').select('*').eq('id', route_id).execute()
        
        if not existing.data:
            return jsonify({'success': False, 'error': 'Route not found'}), 404
        
        db.client.table('phone_routing').update({'is_active': False}).eq('id', route_id).execute()
        
        logger.info(f"✅ Route deactivated: {route_id}")
        
        return jsonify({
            'success': True,
            'message': 'Route deactivated successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error deleting route: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# TRACKING
# ============================================================================

def get_tracking_sources() -> tuple[Dict[str, Any], int]:
    """Lista tracking sources."""
    try:
        utm_source = request.args.get('utm_source')
        utm_campaign = request.args.get('utm_campaign')
        limit = int(request.args.get('limit', 50))
        
        query = db.client.table('tracking_sources').select('*')
        
        if utm_source:
            query = query.eq('utm_source', utm_source)
        
        if utm_campaign:
            query = query.eq('utm_campaign', utm_campaign)
        
        query = query.order('last_call_at', desc=True, nulls_last=True).limit(limit)
        
        result = query.execute()
        
        sources_with_stats = []
        for source in result.data:
            stats = db.client.table('calls').select(
                'call_sid',
                count='exact'
            ).eq('tracking_source_id', source['id']).execute()
            
            source['total_calls'] = stats.count or 0
            sources_with_stats.append(source)
        
        return jsonify({
            'success': True,
            'count': len(sources_with_stats),
            'sources': sources_with_stats
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error fetching tracking sources: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def get_tracking_number() -> tuple[Dict[str, Any], int]:
    """Retorna número de tracking baseado em UTM."""
    try:
        params = {
            'utm_source': request.args.get('utm_source'),
            'utm_medium': request.args.get('utm_medium'),
            'utm_campaign': request.args.get('utm_campaign'),
            'utm_content': request.args.get('utm_content'),
            'utm_term': request.args.get('utm_term'),
            'gclid': request.args.get('gclid')
        }
        
        default_route = db.client.table('phone_routing').select(
            'tracking_number'
        ).eq('is_active', True).is_('campaign', 'null').limit(1).execute()
        
        if not default_route.data:
            return jsonify({
                'success': False,
                'error': 'No tracking numbers available'
            }), 404
        
        tracking_number = default_route.data[0]['tracking_number']
        
        if any(params.values()):
            params['tracking_number'] = tracking_number
            db.get_or_create_tracking_source(params)
        
        return jsonify({
            'success': True,
            'phone_number': tracking_number,
            'formatted': _format_phone_br(tracking_number),
            'utm_params': params
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error getting tracking number: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ANALYTICS
# ============================================================================

def get_analytics_summary() -> tuple[Dict[str, Any], int]:
    """Retorna resumo de analytics."""
    try:
        total_calls = db.client.table('calls').select('*', count='exact').execute()
        completed = db.client.table('calls').select('*', count='exact').eq('status', 'completed').execute()
        recorded = db.client.table('calls').select('*', count='exact').not_.is_('recording_url', 'null').execute()
        
        return jsonify({
            'success': True,
            'summary': {
                'total_calls': total_calls.count,
                'completed_calls': completed.count,
                'recorded_calls': recorded.count,
                'conversion_rate': round((completed.count / total_calls.count * 100) if total_calls.count > 0 else 0, 2)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error fetching analytics: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# DOCUMENTAÇÃO
# ============================================================================

def api_docs():
    """Documentação da API"""
    docs = {
        'version': '2.0.0',
        'endpoints': {
            'routing': {
                'GET /api/routing': 'Lista todas as rotas',
                'POST /api/routing': 'Cria nova rota',
                'GET /api/routing/<id>': 'Busca rota específica',
                'PUT /api/routing/<id>': 'Atualiza rota',
                'DELETE /api/routing/<id>': 'Desativa rota'
            },
            'tracking': {
                'GET /api/tracking/sources': 'Lista tracking sources',
                'GET /api/tracking/get-number': 'Retorna número baseado em UTM'
            },
            'analytics': {
                'GET /api/analytics/summary': 'Resumo de estatísticas'
            }
        }
    }
    return jsonify(docs), 200


# ============================================================================
# FUNÇÕES AUXILIARES
# ============================================================================

def _format_phone_br(phone: str) -> str:
    """Formata número brasileiro."""
    if phone.startswith('+55'):
        clean = phone[3:]
        if len(clean) == 11:
            return f"({clean[:2]}) {clean[2:7]}-{clean[7:]}"
        elif len(clean) == 10:
            return f"({clean[:2]}) {clean[2:6]}-{clean[6:]}"
    return phone