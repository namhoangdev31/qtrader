from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(title='python-ml-inference', version='2.0.0')


@app.get('/health')
async def health() -> dict[str, str]:
    return {'service': 'python-ml-inference', 'status': 'ok'}


@app.post('/predict/regime')
async def predict_regime(features: dict[str, Any]) -> dict[str, str]:
    strength = float(features.get('strength', 0.0))
    if strength > 0.6:
        regime = 'TRENDING'
    elif strength < 0.2:
        regime = 'MEAN_REVERTING'
    else:
        regime = 'NEUTRAL'
    return {'regime': regime}
