import json
from typing import Any, Callable, Dict, Optional, List
import asyncio

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

class RedisStateManager:
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis = None
        self.pubsub = None
        self.is_mock = redis_url == "mock" or not REDIS_AVAILABLE
        self.mock_storage = {}
        self.mock_subscribers = {}
        
        if not REDIS_AVAILABLE and redis_url != "mock":
            print("[WARNING] Redis library not found. Forcing MOCK mode.")

    async def connect(self):
        """Establish connection to Redis."""
        if not self.is_mock:
            self.redis = redis.from_url(self.redis_url, decode_responses=True)
            self.pubsub = self.redis.pubsub()
        else:
            print("[WARNING] Running in MOCK Redis mode (In-Memory)")

    async def set_state(self, key: str, value: Any, expire: int = None):
        """Asynchronously save state to Redis."""
        if self.is_mock:
            self.mock_storage[key] = value
            return

        if not self.redis:
            await self.connect()
        await self.redis.set(key, json.dumps(value), ex=expire)

    async def get_state(self, key: str) -> Optional[Any]:
        """Asynchronously retrieve state from Redis."""
        if self.is_mock:
            return self.mock_storage.get(key)

        if not self.redis:
            await self.connect()
        value = await self.redis.get(key)
        return json.loads(value) if value else None

    async def publish_event(self, channel: str, message: Dict[str, Any]):
        """Publish an event to a Redis channel."""
        if self.is_mock:
            if channel in self.mock_subscribers:
                for callback in self.mock_subscribers[channel]:
                    asyncio.create_task(callback(channel, message))
            return

        if not self.redis:
            await self.connect()
        await self.redis.publish(channel, json.dumps(message))

    async def listen(self, channels: List[str], callback: Callable[[str, Dict], Any]):
        """
        Listen to specific channels and trigger callback.
        """
        if self.is_mock:
            for channel in channels:
                if channel not in self.mock_subscribers:
                    self.mock_subscribers[channel] = []
                self.mock_subscribers[channel].append(callback)
            # Keep the task alive
            while True:
                await asyncio.sleep(1)
            return

        if not self.redis:
            await self.connect()
        
        await self.pubsub.subscribe(*channels)
        
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"]
                data = json.loads(message["data"])
                # Run callback asynchronously
                asyncio.create_task(callback(channel, data))

    async def close(self):
        if self.redis:
            await self.redis.close()
