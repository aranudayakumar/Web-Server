from typing import List
import datetime as _dt
import pydantic as _pydantic


class _UserBase(_pydantic.BaseModel):
    username: str


class UserCreate(_UserBase):
    password: str


class User(_UserBase):
    id: int

    class Config:
        orm_mode = True