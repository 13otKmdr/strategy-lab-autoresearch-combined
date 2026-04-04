from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cycles import router as cycles_router
from app.api.strategies import router as strategies_router

app = FastAPI(
    title="StrategyLab",
    description="Trading strategy research platform — generate, backtest, rank, and analyze day trading strategies",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cycles_router, prefix="/api")
app.include_router(strategies_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "strategylab"}
