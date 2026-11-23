import json


async def fetch_and_parse(url: str):
    # Contextless re-raise inside async def
    try:
        response = await get(url)
    except Exception as err:
        raise err

    # Nested try with bare raise and ellipsis
    try:
        try:
            parsed = json.loads(response)
        except (ValueError, Exception):
            raise
    except:
        ...
