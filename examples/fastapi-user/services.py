#services.py

import sqlalchemy.orm as _orm

import models as _models, schemas as _schemas, database as _database
from passlib.hash import bcrypt


def create_database():
    return _database.Base.metadata.create_all(bind=_database.engine)


def get_db():
    db = _database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_user(db: _orm.Session, user_id: int):
    return db.query(_models.User).filter(_models.User.id == user_id).first()

def verify_password(db: _orm.Session,username: str, password: str):
    user_obj = db.query(_models.User).filter(_models.User.username == username).first()
    # print(user_obj.password_hash)
    # print(password)
    # print(bcrypt.verify(password, user_obj.password_hash))
    return bcrypt.verify(password, user_obj.password_hash)


def get_user_by_username(db: _orm.Session, username: str):
    return db.query(_models.User).filter(_models.User.username == username).first()


def get_users(db: _orm.Session, skip: int = 0, limit: int = 100):
    return db.query(_models.User).offset(skip).limit(limit).all()


def create_user(db: _orm.Session, user: _schemas.UserCreate):
    db_user = _models.User(username=user.username, password_hash=bcrypt.hash(user.password))
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user