"""Optional standard-client probe; run in an environment with the official mcp SDK."""
import asyncio
import json
import sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


async def main():
    with open(sys.argv[1], encoding='utf-8') as stream:
        invitation = json.load(stream)
    async with streamablehttp_client(invitation['url'], headers={'Authorization': 'Bearer ' + invitation['token']}) as (read, write, _):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.protocolVersion == '2025-06-18'
            assert not init.capabilities.resources.subscribe
            listing = await session.list_tools()
            assert {t.name for t in listing.tools} == {'get_state', 'get_connection_info', 'legal_moves', 'make_move', 'wait_for_move', 'get_pgn'}
            resource = await session.read_resource('chess://game/state')
            assert resource.contents
            state = (await session.call_tool('get_state')).structuredContent
            assert state['caller_can_move']
            result = await session.call_tool('make_move', {'move': 'e2e4', 'game_id': state['game_id'], 'expected_fen': state['fen']})
            assert not result.isError, result
            waiting = await session.call_tool('wait_for_move', {'timeout': 0, 'game_id': state['game_id']})
            assert not waiting.isError and waiting.structuredContent['timeout']
            assert 'e4' in (await session.call_tool('get_pgn')).structuredContent['pgn']
    print('Standard MCP client: initialize, list, resource, state, move, wait and close passed.')


if __name__ == '__main__':
    asyncio.run(main())
