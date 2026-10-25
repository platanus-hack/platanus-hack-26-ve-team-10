from fastapi import APIRouter
from fastapi.responses import Response

from app.agents.card_image import read_card_image

router = APIRouter()


@router.get("/card-images/{token}.jpg")
async def card_image(token: str):
    data = read_card_image(token)
    if data is None:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
