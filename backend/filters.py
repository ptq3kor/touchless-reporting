"""Shared filter contract: query params -> resolved SQL fragments and metadata."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional

if TYPE_CHECKING:
    from .db import ConnectionWrapper

from fastapi import Query
from pydantic import BaseModel


class FilterParams(BaseModel):
    year: int = 2024
    month: int = 5
    sector: Literal["BBM", "BBI", "BBG", "BBE", "ALL"] = "ALL"
    area: Optional[str] = None
    subregion: Optional[str] = None
    country: Optional[str] = None
    entity_id: Optional[int] = None
    division: Optional[str] = None
    currency: Literal["EUR", "LOCAL"] = "EUR"
    view: Literal["NOM", "REAL"] = "NOM"
    cmp: Literal["CF", "BP"] = "CF"


def filter_params(
    year: int = Query(2024, ge=2023, le=2024),
    month: int = Query(5, ge=1, le=12),
    sector: Literal["BBM", "BBI", "BBG", "BBE", "ALL"] = "ALL",
    area: Optional[str] = None,
    subregion: Optional[str] = None,
    country: Optional[str] = None,
    entity_id: Optional[int] = None,
    division: Optional[str] = None,
    currency: Literal["EUR", "LOCAL"] = "EUR",
    view: Literal["NOM", "REAL"] = "NOM",
    cmp: Literal["CF", "BP"] = "CF",
) -> FilterParams:
    return FilterParams(
        year=year, month=month, sector=sector, area=area, subregion=subregion,
        country=country, entity_id=entity_id, division=division,
        currency=currency, view=view, cmp=cmp,
    )


@dataclass
class Resolved:
    fp: FilterParams
    period_id: int
    py_period_id: int
    ytd_start: int
    py_ytd_start: int
    where: str            # extra WHERE fragment for fact_financials alias `f` (starts with " AND" or empty)
    params: dict          # named params used by `where`
    val_col: str          # value column to aggregate for the user-facing figure
    currency_used: str    # "EUR" or "LOCAL"
    currency_note: Optional[str] = None
    local_currency: Optional[str] = None
    entity_ids: Optional[list] = field(default=None)  # None = unrestricted

    def meta(self) -> dict:
        return {
            "period_id": self.period_id,
            "sector": self.fp.sector,
            "currency_used": self.currency_used,
            "local_currency": self.local_currency,
            "view": self.fp.view,
            "cmp": self.fp.cmp,
            "currency_note": self.currency_note,
        }


def _scoped_entities(conn: "ConnectionWrapper", fp: FilterParams):
    """Resolve geography/entity filters to entity ids and their currency set.

    Returns (entity_ids or None, set of currency codes in scope).
    """
    sql = """SELECT e.entity_id, c.currency_code
             FROM dim_legal_entity e JOIN dim_country c ON c.country_code = e.country_code
             WHERE 1=1"""
    params: dict = {}
    restricted = False
    if fp.entity_id is not None:
        sql += " AND e.entity_id = :entity_id"
        params["entity_id"] = fp.entity_id
        restricted = True
    if fp.country:
        sql += " AND c.country_code = :country"
        params["country"] = fp.country
        restricted = True
    if fp.subregion:
        sql += " AND c.subregion = :subregion"
        params["subregion"] = fp.subregion
        restricted = True
    if fp.area:
        sql += " AND c.area = :area"
        params["area"] = fp.area
        restricted = True
    rows = conn.execute(sql, params).fetchall()
    currencies = {r["currency_code"] for r in rows}
    return ([r["entity_id"] for r in rows] if restricted else None), currencies


def resolve(conn: "ConnectionWrapper", fp: FilterParams, sector_filter: bool = True) -> Resolved:
    period_id = fp.year * 100 + fp.month
    entity_ids, currencies = _scoped_entities(conn, fp)

    where = ""
    params: dict = {}
    if sector_filter and fp.sector != "ALL":
        where += " AND f.sector_code = :sector"
        params["sector"] = fp.sector
    if fp.division:
        where += " AND f.division_code = :division"
        params["division"] = fp.division
    if entity_ids is not None:
        keys = []
        for i, eid in enumerate(entity_ids):
            k = f"ent{i}"
            params[k] = eid
            keys.append(f":{k}")
        where += f" AND f.entity_id IN ({', '.join(keys) or 'NULL'})"

    currency_used, note, local_ccy = "EUR", None, None
    if fp.currency == "LOCAL":
        if len(currencies) == 1:
            currency_used = "LOCAL"
            local_ccy = next(iter(currencies))
        else:
            note = "Local currency requires a single-currency selection; showing EUR."

    if currency_used == "LOCAL":
        val_col = "value_lc"
    elif fp.view == "REAL":
        val_col = "value_eur_real"
    else:
        val_col = "value_eur_nom"

    return Resolved(
        fp=fp,
        period_id=period_id,
        py_period_id=period_id - 100,
        ytd_start=fp.year * 100 + 1,
        py_ytd_start=(fp.year - 1) * 100 + 1,
        where=where,
        params=params,
        val_col=val_col,
        currency_used=currency_used,
        currency_note=note,
        local_currency=local_ccy,
        entity_ids=entity_ids,
    )
