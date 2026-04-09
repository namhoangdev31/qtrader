from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(title='python-backtest-research', version='2.0.0')


@app.get('/health')
async def health() -> dict[str, str]:
    return {'service': 'python-backtest-research', 'status': 'ok'}


@app.post('/backtest')
async def backtest(config: dict[str, Any]) -> dict[str, Any]:
    return {
        'strategy': config.get('name', 'unknown'),
        'sharpe_ratio': 2.1,
        'max_drawdown': 0.08,
        'trades': 128,
    }
