import asyncio
import numpy as np
import json
from qtrader.ml.ollama_forecast_adapter import OllamaForecastAdapter
from qtrader.ml.ollama_risk_adapter import OllamaRiskAdapter

async def test_parsing():
    print("=== Testing Ollama Parsing Resilience ===")
    
    # 1. Test Forecast Parser with various malformations
    forecast_adapter = OllamaForecastAdapter("test", "http://localhost:11434")
    
    test_cases = [
        ('{"forecast": [10.5, 11.2, 12.1]}', "Standard JSON"),
        ('```json\n{"forecast": [10.5, 11.2, 12.1]}\n```', "Markdown wrapped"),
        ('The forecast is: {"forecast": [10.5, 11.2, 12.1]} and it looks good.', "Conversational text"),
        ('{"predictions": [10.5, 11.2, 12.1]}', "Alternative key name"),
        ('{"forecast": [10.5, 11.2, 12.1]', "Truncated (missing closing brace)"),
        ('{"forecast": [10.5, 11.2', "Severely truncated"),
    ]
    
    for text, desc in test_cases:
        try:
            result = forecast_adapter._parse_forecast(text)
            print(f"DEBUG: {desc} -> SUCCESS: {result}")
        except Exception as e:
            print(f"DEBUG: {desc} -> FAILED: {e}")

    # 2. Test Risk Parser
    risk_adapter = OllamaRiskAdapter("test", "http://localhost:11434")
    risk_cases = [
        ('{"class_label": "SAFE", "confidence": 0.9, "risk_score": 0.1}', "Standard Risk"),
        ('{"label": "DANGER", "conf": 0.8}', "Incomplete keys"),
        ('{"class_label": "SAFE", "confidence": 0.9', "Truncated Risk"),
    ]
    
    for text, desc in risk_cases:
        try:
            result = risk_adapter._parse_risk_response(text)
            print(f"DEBUG: {desc} -> SUCCESS: {result.class_label} (conf={result.confidence})")
        except Exception as e:
            print(f"DEBUG: {desc} -> FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_parsing())
