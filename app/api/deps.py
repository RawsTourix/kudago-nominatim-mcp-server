from typing import Annotated

from arq.connections import ArqRedis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session


DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_arq_redis(request: Request) -> ArqRedis:
    return request.app.state.arq_redis


ArqPool = Annotated[ArqRedis, Depends(get_arq_redis)]