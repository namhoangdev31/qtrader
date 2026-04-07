import asyncio
import logging
from decimal import Decimal
from datetime import datetime

from qtrader.persistence.db_writer import TradeDBWriter
from qtrader.core.dynamic_config import config_manager
from qtrader.core.db import DBClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_audit_verify")

async def main():
    writer = TradeDBWriter()
    
    print("\n[STP 1] NUCLEAR RESET — PURGING ENTIRE DATABASE")
    await writer.purge_database()
    print("[SUCCESS] All tables purged and reconstructed.")
    
    print("\n[STP 2] STARTING AUDIT SESSION")
    session_id = await writer.start_session(
        initial_capital=Decimal("100000.0"),
        metadata={"mode": "AUDIT_VERIFICATION", "trigger": "MANUAL_TEST"}
    )
    print(f"[SUCCESS] Session started: {session_id}")
    
    print("\n[STP 3] SIMULATING AI-DRIVEN CONFIGURATION SHIFT")
    def audit_callback(key, old_v, new_v):
        asyncio.create_task(
            writer.write_config_change(
                session_id=session_id,
                parameter=key,
                old_value=old_v,
                new_value=new_v,
                changed_by="AI_VERIFIER"
            )
        )
    
    config_manager.register_callback(audit_callback)
    
    old_min_conf = config_manager.get("MIN_CONFIDENCE")
    new_min_conf = 0.85
    print(f"[ACTION] Shifting MIN_CONFIDENCE: {old_min_conf} -> {new_min_conf}")
    config_manager.set_override("MIN_CONFIDENCE", new_min_conf)
    
    await asyncio.sleep(2)
    
    print("\n[STP 4] VERIFYING AUDIT TRAIL RECORD")
    query = "SELECT * FROM config_changes ORDER BY timestamp DESC LIMIT 1"
    rows = await DBClient.fetch(query)
    
    if rows:
        row = rows[0]
        print(f"[SUCCESS] Audit Record Found:")
        print(f"  - Parameter:  {row['parameter']}")
        print(f"  - Old Value:  {row['old_value']}")
        print(f"  - New Value:  {row['new_value']}")
        print(f"  - Changed By: {row['changed_by']}")
        print(f"  - Timestamp:  {row['timestamp']}")
    else:
        print("[FAIL] No audit record found in config_changes table.")

    print("\n[STP 5] FINAL CLEANUP")
    await DBClient.close_all()
    print("[DONE]")

if __name__ == "__main__":
    asyncio.run(main())
