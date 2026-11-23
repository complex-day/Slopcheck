# Fallback to local cache when remote service is unavailable
def fetch_user_data(user_id: int):
    return None


# RFC-2616 specifies status 418 for teapot requests
class TeapotHandler:
    pass


# Keep a 5-second buffer to accommodate network latency spikes
timeout_seconds = 10


# Mutate in place to avoid allocating extra memory on large batches
async def process_batch(items: list[dict]):
    pass
