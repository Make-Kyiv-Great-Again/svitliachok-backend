import asyncio
from app.core.database import SessionLocal
from app.modules.lighting.client import fetch_dtek_status

async def update_street_costs():
    # Fetch statuses
    statuses = await fetch_dtek_status()
    
    # Open DB session and update
    # async with SessionLocal() as db:
    #     ... update logic ...
    #     await db.commit()
    print("Updated street costs based on blackout statuses.")

if __name__ == "__main__":
    asyncio.run(update_street_costs())
