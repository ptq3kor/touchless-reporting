from fastapi import APIRouter, Depends

from .. import queries
from ..db import get_conn
from ..filters import FilterParams, filter_params, resolve

router = APIRouter(prefix="/api", tags=["headcount"])


@router.get("/headcount")
def get_headcount(fp: FilterParams = Depends(filter_params)):
    conn = get_conn()
    try:
        return queries.headcount_data(conn, resolve(conn, fp))
    finally:
        conn.close()
