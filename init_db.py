"""
Initialize database tables.
"""

import asyncio
from core.database import engine
from core.models import Base

async def init_db():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables created successfully!")

if __name__ == "__main__":
    asyncio.run(init_db())