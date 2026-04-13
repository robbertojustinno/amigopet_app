import json
from app.core.config import settings

try:
    import redis
except Exception:
    redis = None

class RedisService:
    def __init__(self):
        self.client = None
        if redis is not None:
            try:
                self.client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
                self.client.ping()
            except Exception:
                self.client = None

    def publish(self, channel: str, payload: dict):
        if not self.client:
            return False
        self.client.publish(channel, json.dumps(payload))
        return True

    def set_cache(self, key: str, payload: dict, ttl: int = 60):
        if not self.client:
            return False
        self.client.setex(key, ttl, json.dumps(payload))
        return True

redis_service = RedisService()
