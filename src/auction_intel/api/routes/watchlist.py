from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auction_intel.db import models
from auction_intel.db.database import get_db

router = APIRouter()


class WatchlistCreate(BaseModel):
    title: str
    district: str
    area_m2: float
    bedrooms: int
    parking_spaces: int
    bathrooms: int
    auction_price: float
    ml_predicted_price: float
    roi_potential: float
    itbi_price: float | None = None
    link: str
    image_url: str = None
    owner_id: int


@router.post("/")
def save_to_watchlist(item: WatchlistCreate, db: Session = Depends(get_db)):
    try:
        new_item = models.Watchlist(**item.model_dump(), status="Monitorando")
        db.add(new_item)
        db.commit()
        return {"message": "Imóvel salvo com sucesso!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


# Agora buscamos pela Watchlist DE UM USUÁRIO ESPECÍFICO
@router.get("/{user_id}")
def list_watchlist(user_id: int, db: Session = Depends(get_db)):
    try:
        return db.query(models.Watchlist).filter(models.Watchlist.owner_id == user_id).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{item_id}")
def delete_from_watchlist(item_id: int, db: Session = Depends(get_db)):
    item = db.query(models.Watchlist).filter(models.Watchlist.id == item_id).first()
    if item:
        db.delete(item)
        db.commit()
        return {"message": "Deletado com sucesso"}
    raise HTTPException(status_code=404, detail="Item não encontrado")
