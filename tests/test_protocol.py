from mcp import Client
from cachyos_mcp.config import Settings, PROJECT
from cachyos_mcp.server import create_server

async def test_initialization_and_system_tools(tmp_path):
    server = create_server(Settings(log_directory=str(tmp_path)))
    async with Client(server) as client:
        tools = await client.list_tools()
        assert any(t.name == 'get_system_info' for t in tools.tools)
        result = await client.call_tool('get_memory_info')
        assert not result.is_error
        assert result.structured_content['data']['total'] > 0
        result = await client.call_tool('get_system_info')
        assert result.structured_content['data']['os']['ID'] == 'cachyos'

async def test_real_stdio():
    from mcp import StdioServerParameters
    async with Client(StdioServerParameters(command=str(PROJECT / 'scripts/launch.sh'))) as client:
        result = await client.call_tool('get_kernel_info')
        assert result.structured_content['success']
        assert 'cachyos' in result.structured_content['data']['release']
