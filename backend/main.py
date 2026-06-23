from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import assistant, headcount, meta, nwc, pnl, sales, sga, summary

app = FastAPI(title="Touchless Reporting API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://*.cfapps.eu10.hana.ondemand.com",
    ],
    allow_origin_regex=r"https://.*\.cfapps\.eu10\.hana\.ondemand\.com",
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (meta, sales, pnl, sga, headcount, nwc, summary, assistant):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
