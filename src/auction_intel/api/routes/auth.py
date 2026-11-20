from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auction_intel.db import models
from auction_intel.db.database import get_db

router = APIRouter()

# Configuração do encriptador de senhas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserAuth(BaseModel):
    email: str
    password: str


@router.post("/registrar")
def register_user(user: UserAuth, db: Session = Depends(get_db)):
    # Verifica se o email já existe
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    # Criptografa a senha e salva
    hashed_password = pwd_context.hash(user.password)
    new_user = models.User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"id": new_user.id, "email": new_user.email}


@router.post("/login")
def login_user(user: UserAuth, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    # Verifica se o usuário existe e se a senha bate com a criptografia
    if not db_user or not pwd_context.verify(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="E-mail ou senha incorretos.")

    return {"id": db_user.id, "email": db_user.email}
