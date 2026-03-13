import asyncio
import logging
import signal
import sys
import uvicorn
from datetime import datetime
from qtrader.core.config import Config
from qtrader.core.db import DBClient
from qtrader.api.api import app as fastapi_app, stats
from scripts.verify_v4_autonomous import verify_v4_autonomous_intelligence

logger = logging.getLogger("LiveEngine")

class LiveEngine:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *args):
        logger.info("🛑 Shutdown signal received. Cleaning up...")
        self.running = False
        stats["status"] = "Shutting Down"

    async def run_api(self):
        """Runs the FastAPI server."""
        config = uvicorn.Config(fastapi_app, host="0.0.0.0", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()

    async def trading_loop(self):
        """Main autonomous trading logic."""
        logger.info("🚀 QTrader v4 Autonomous Live Engine Starting...")
        stats["status"] = "Initializing"
        
        # Initial health check
        await verify_v4_autonomous_intelligence()
        
        stats["status"] = "Running"
        iteration = 0
        while self.running:
            iteration += 1
            now = datetime.now()
            stats["iteration"] = iteration
            stats["last_heartbeat"] = now
            
            try:
                logger.info(f"🔄 Loop #{iteration} | Heartbeat | Time: {now}")
                
                # Update mock stats for the API
                stats["regime"] = "Bull" if iteration % 2 == 0 else "Sideways"
                stats["active_model"] = "Model_Bull" if stats["regime"] == "Bull" else "Model_Sideways"
                stats["exposure_btc"] = 0.5 + (iteration * 0.01)
                
                await asyncio.sleep(1)
                
                pool = await DBClient.get_pool()
                await pool.fetchval("SELECT 1")
                
            except Exception as e:
                logger.error(f"⚠️ Error in loop: {e}")
                stats["status"] = f"Error: {str(e)}"
                await asyncio.sleep(5)
                
            await asyncio.sleep(9)

    async def main(self):
        # Run both the API and the Trading loop concurrently
        await asyncio.gather(
            self.run_api(),
            self.trading_loop()
        )

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    engine = LiveEngine()
    try:
        asyncio.run(engine.main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"💥 Fatal crash: {e}")
        sys.exit(1)
