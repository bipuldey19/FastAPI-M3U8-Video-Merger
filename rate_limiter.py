"""
Rate limiting middleware using Redis
"""
import time
from functools import wraps
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from config import settings
import logging

logger = logging.getLogger(__name__)


def rate_limit(max_requests: int = 10, window: int = 60):
    """
    Rate limiting decorator
    Args:
        max_requests: Maximum number of requests allowed
        window: Time window in seconds
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request object from kwargs
            request = kwargs.get('request')
            if not request:
                # Try to find it in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if not request:
                # If no request found, skip rate limiting
                return await func(*args, **kwargs)
            
            # Get client IP
            client_ip = request.client.host
            
            # Create Redis key
            key = f"rate_limit:{client_ip}:{func.__name__}"
            
            try:
                redis_client = await redis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True
                )
                
                # Get current count
                current = await redis_client.get(key)
                
                if current is None:
                    # First request in window
                    await redis_client.setex(key, window, 1)
                elif int(current) >= max_requests:
                    # Rate limit exceeded
                    ttl = await redis_client.ttl(key)
                    raise HTTPException(
                        status_code=429,
                        detail=f"Rate limit exceeded. Try again in {ttl} seconds.",
                        headers={"Retry-After": str(ttl)}
                    )
                else:
                    # Increment counter
                    await redis_client.incr(key)
                
                await redis_client.close()
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Rate limiting error: {e}")
                # Continue without rate limiting if Redis fails
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
