"""Database connection layer — SAP HANA Cloud.

Provides get_conn() returning a connection wrapper that is API-compatible
with the sqlite3.Connection interface used throughout queries.py and filters.py:
  - conn.execute(sql, params) supports both named (:name) and positional (?) params
  - Rows support dict-style access: row["column_name"] and dict(row)
  - conn.close() releases the HANA connection
"""
import os
import re
from decimal import Decimal
from pathlib import Path

# Load .env from project root
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        with open(_ENV_FILE) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

# HANA connection parameters from environment
HANA_HOST = os.getenv("HANA_HOST", "")
HANA_PORT = int(os.getenv("HANA_PORT", "443"))
HANA_USER = os.getenv("HANA_USER", "")
HANA_PASSWORD = os.getenv("HANA_PASSWORD", "")
HANA_SCHEMA = os.getenv("HANA_SCHEMA", "")
HANA_ENCRYPT = os.getenv("HANA_ENCRYPT", "true").lower() == "true"

# Regex to find :named_param tokens (but not ::cast or inside strings)
_NAMED_PARAM_RE = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


class DictRow:
    """A row that supports both row["col"] dict access and dict(row) conversion."""

    __slots__ = ("_data", "_keys")

    def __init__(self, keys: list, values: tuple):
        self._keys = keys
        # Convert Decimal → float for JSON compatibility
        self._data = {k: (float(v) if isinstance(v, Decimal) else v)
                      for k, v in zip(keys, values)}

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._data.values())[key]
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def __iter__(self):
        return iter(self._data.values())

    def __len__(self):
        return len(self._data)

    def keys(self):
        return self._keys

    def values(self):
        return list(self._data.values())

    def items(self):
        return self._data.items()


class CursorWrapper:
    """Wraps a HANA cursor to return DictRow objects and support named params."""

    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = []
        self._rows = []
        self._pos = 0

    def _translate_params(self, sql: str, params):
        """Convert :named params to ? positional params for HANA.

        If params is a dict and sql has :name placeholders, translate them.
        If params is a list/tuple and sql has ? placeholders, pass through.
        """
        if params is None:
            return sql, []

        if isinstance(params, dict):
            # Find all :name tokens and replace with ?, building ordered param list
            ordered_params = []
            def replacer(match):
                name = match.group(1)
                ordered_params.append(params[name])
                return "?"
            translated_sql = _NAMED_PARAM_RE.sub(replacer, sql)
            return translated_sql, ordered_params
        else:
            # Already positional (tuple or list)
            return sql, list(params)

    def execute(self, sql: str, params=None):
        sql, param_list = self._translate_params(sql, params)
        if param_list:
            self._cursor.execute(sql, param_list)
        else:
            self._cursor.execute(sql)
        # Cache column names from cursor description
        if self._cursor.description:
            self._columns = [desc[0].lower() for desc in self._cursor.description]
        else:
            self._columns = []
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return DictRow(self._columns, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        return [DictRow(self._columns, row) for row in rows]

    def __iter__(self):
        """Support iteration over results (for r in conn.execute(...))."""
        rows = self._cursor.fetchall()
        return iter(DictRow(self._columns, row) for row in rows)


class ConnectionWrapper:
    """Wraps a HANA dbapi connection to provide sqlite3-like interface."""

    def __init__(self, hana_conn):
        self._conn = hana_conn

    def execute(self, sql: str, params=None):
        cursor = CursorWrapper(self._conn.cursor())
        return cursor.execute(sql, params)

    def close(self):
        self._conn.close()


def get_conn() -> ConnectionWrapper:
    """Create a new HANA Cloud connection with dict-row support."""
    from hdbcli import dbapi

    conn = dbapi.connect(
        address=HANA_HOST,
        port=HANA_PORT,
        user=HANA_USER,
        password=HANA_PASSWORD,
        encrypt=HANA_ENCRYPT,
        sslValidateCertificate=True,
    )
    # Set schema
    if HANA_SCHEMA:
        cursor = conn.cursor()
        cursor.execute(f'SET SCHEMA "{HANA_SCHEMA}"')
        cursor.close()

    return ConnectionWrapper(conn)
