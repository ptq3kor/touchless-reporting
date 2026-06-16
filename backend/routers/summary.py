from fastapi import APIRouter, Depends

from .. import queries
from ..db import get_conn
from ..filters import FilterParams, filter_params, resolve

router = APIRouter(prefix="/api", tags=["summary"])


@router.get("/summary")
def get_summary(fp: FilterParams = Depends(filter_params)):
    conn = get_conn()
    try:
        return queries.summary_data(conn, resolve(conn, fp))
    finally:
        conn.close()
