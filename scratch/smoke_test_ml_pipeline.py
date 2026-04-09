
import asyncio
import logging
from decimal import Decimal
from qtrader.ml.atomic_trio import AtomicTrioPipeline

async def smoke_test():
    logging.basicConfig(level=logging.INFO)
    pipeline = AtomicTrioPipeline()
    
    print("Running AtomicTrioPipeline Smoke Test...")
    try:
        # Mocking minimal input
        result = await pipeline.run(
            historical_prices=[70000.0, 71000.0, 72000.0] * 10,
            market_features={"rsi": 50.0},
            market_context={"trend": "sideways"}
        )
        
        print(f"Success! Pipeline Result Attributes:")
        print(f" - decision: {result.decision.action}")
        print(f" - chronos_forecast: {result.chronos_forecast is not None}")
        print(f" - tabpfn_risk: {result.tabpfn_risk is not None}")
        
    except Exception as e:
        print(f"Smoke Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(smoke_test())
