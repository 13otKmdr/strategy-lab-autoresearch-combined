"""
SQLite storage layer for persisting cycles, strategies, and results.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.config import DATABASE_PATH


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cycles (
            cycle_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            summary_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS strategies (
            strategy_id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            definition_json TEXT NOT NULL,
            FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
        );

        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            risk_pct REAL NOT NULL,
            result_json TEXT NOT NULL,
            equity_curve_json TEXT,
            drawdown_curve_json TEXT,
            FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id),
            FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
        );

        CREATE TABLE IF NOT EXISTS rankings (
            strategy_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            ranking_json TEXT NOT NULL,
            PRIMARY KEY (strategy_id, cycle_id),
            FOREIGN KEY (strategy_id) REFERENCES strategies(strategy_id),
            FOREIGN KEY (cycle_id) REFERENCES cycles(cycle_id)
        );

        CREATE INDEX IF NOT EXISTS idx_strategies_cycle ON strategies(cycle_id);
        CREATE INDEX IF NOT EXISTS idx_results_cycle ON backtest_results(cycle_id);
        CREATE INDEX IF NOT EXISTS idx_results_strategy ON backtest_results(strategy_id);
        CREATE INDEX IF NOT EXISTS idx_rankings_cycle ON rankings(cycle_id);
    """)
    conn.commit()
    conn.close()


def save_cycle(cycle_id: str, timestamp: str, summary: dict):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO cycles (cycle_id, timestamp, summary_json) VALUES (?, ?, ?)",
        (cycle_id, timestamp, json.dumps(summary)),
    )
    conn.commit()
    conn.close()


def save_strategy(strategy_id: str, cycle_id: str, definition: dict):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO strategies (strategy_id, cycle_id, definition_json) VALUES (?, ?, ?)",
        (strategy_id, cycle_id, json.dumps(definition)),
    )
    conn.commit()
    conn.close()


def save_backtest_result(
    strategy_id: str,
    cycle_id: str,
    risk_pct: float,
    result: dict,
    equity_curve: list[float],
    drawdown_curve: list[float],
):
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO backtest_results
           (strategy_id, cycle_id, risk_pct, result_json, equity_curve_json, drawdown_curve_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (strategy_id, cycle_id, risk_pct, json.dumps(result),
         json.dumps(equity_curve), json.dumps(drawdown_curve)),
    )
    conn.commit()
    conn.close()


def save_ranking(strategy_id: str, cycle_id: str, rank: int, ranking: dict):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO rankings (strategy_id, cycle_id, rank, ranking_json) VALUES (?, ?, ?, ?)",
        (strategy_id, cycle_id, rank, json.dumps(ranking)),
    )
    conn.commit()
    conn.close()


def get_cycles() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT cycle_id, timestamp, summary_json FROM cycles ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [{"cycle_id": r["cycle_id"], "timestamp": r["timestamp"], **json.loads(r["summary_json"])} for r in rows]


def get_cycle(cycle_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT summary_json FROM cycles WHERE cycle_id = ?", (cycle_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row["summary_json"])


def get_strategy(strategy_id: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT definition_json FROM strategies WHERE strategy_id = ?", (strategy_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return json.loads(row["definition_json"])


def get_backtest_results(strategy_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT risk_pct, result_json FROM backtest_results WHERE strategy_id = ? ORDER BY risk_pct",
        (strategy_id,),
    ).fetchall()
    conn.close()
    return [{"risk_pct": r["risk_pct"], **json.loads(r["result_json"])} for r in rows]


def get_equity_curves(strategy_id: str) -> dict:
    conn = get_db()
    rows = conn.execute(
        "SELECT risk_pct, equity_curve_json, drawdown_curve_json FROM backtest_results WHERE strategy_id = ?",
        (strategy_id,),
    ).fetchall()
    conn.close()
    result = {}
    for r in rows:
        key = f"{r['risk_pct']:.2f}"
        result[key] = {
            "equity_curve": json.loads(r["equity_curve_json"]) if r["equity_curve_json"] else [],
            "drawdown_curve": json.loads(r["drawdown_curve_json"]) if r["drawdown_curve_json"] else [],
        }
    return result


def get_rankings(cycle_id: str) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT ranking_json FROM rankings WHERE cycle_id = ? ORDER BY rank",
        (cycle_id,),
    ).fetchall()
    conn.close()
    return [json.loads(r["ranking_json"]) for r in rows]
