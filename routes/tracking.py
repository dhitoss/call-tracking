from fastapi import APIRouter, Query
from typing import Optional

router = APIRouter(prefix='/api/tracking')

@router.get('/get-number')
async def get_tracking_number(
    utm_source: Optional[str] = Query(None),
    utm_medium: Optional[str] = Query(None),
    utm_campaign: Optional[str] = Query(None),
    gclid: Optional[str] = Query(None)
):
    """
    Retorna número de tracking baseado nos parâmetros UTM
    
    Exemplo: /api/tracking/get-number?utm_source=google&utm_campaign=black_friday&gclid=abc123
    """
    # Buscar ou criar tracking source
    source = await db_service.get_or_create_tracking_source(
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        gclid=gclid
    )
    
    # Retornar número formatado
    return {
        "phone_number": source['tracking_number'],
        "formatted": format_phone_br(source['tracking_number']),
        "tracking_id": source['id']
    }