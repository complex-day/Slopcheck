async def _fetch_raw(client, url: str):
    return await client.get(url)


async def _parse_payload(resp):
    data = await resp.json()
    return data["result"]


async def handle_request(client, url: str):
    resp = await _fetch_raw(client, url)
    return await _parse_payload(resp)
