import asyncio
import logging
import signal
import sys
from datetime import datetime
from qtrader.core.config import Config
from qtrader.core.db import DBClient
from scripts.verify_v4_autonomous import verify_v4_autonomous_intelligence

# Configure logging to show timestamps and levels
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("LiveEngine")

class LiveEngine:
    def __init__(self):
        self.running = True
        # Handle termination signals gracefully
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

    def stop(self, *args):
        logger.info("🛑 Shutdown signal received. Cleaning up...")
        self.running = False

    async def run(self):
        logger.info("🚀 QTrader v4 Autonomous Live Engine Starting...")
        logger.info(f"Environment: {'SIMULATION' if Config.SIMULATE_MODE else 'LIVE'}")
        
        # Initial health check
        await verify_v4_autonomous_intelligence()
        
        iteration = 0
        while self.running:
            iteration += 1
            start_time = datetime.now()
            
            try:
                # 1. Market Monitoring & Execution Logic
                # (This is where the real strategies would be called)
                logger.info(f"🔄 Loop #{iteration} | Heartbeat | Time: {start_time}")
                
                # Simulate core work
                await asyncio.sleep(1) # Processing latency simulation
                
                # Check DB connectivity
                pool = await DBClient.get_pool()
                res = await pool.fetchval("SELECT 1")
                if res != 1:
                    logger.error("❌ Database connectivity lost!")
                
            except Exception as e:
                logger.error(f"⚠️ Error in main loop: {e}")
                await asyncio.sleep(5) # Delay on error to avoid rapid failure loops
                
            # Maintain frequency (e.g., every 10 seconds)
            elapsed = (datetime.now() - start_time).total_seconds()
            sleep_time = max(0.1, 10 - elapsed)
            await asyncio.sleep(sleep_time)

        logger.info("✅ QTrader Live Engine has gracefully stopped.")

if __name__ == "__main__":
    engine = LiveEngine()
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"💥 Fatal crash: {e}")
        sys.exit(1)
