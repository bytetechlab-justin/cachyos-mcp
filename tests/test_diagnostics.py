import pytest
from mcp import Client
from cachyos_mcp.config import Settings
from cachyos_mcp.server import create_server

async def test_real_diagnostics(tmp_path):
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        for name, args in [('get_cpu_info', {}), ('get_network_interfaces', {}), ('list_processes', {'limit': 3}), ('list_installed_packages', {'limit': 3}), ('get_service_status', {'name': 'bluetooth'}), ('get_nvidia_status', {}), ('get_temperatures', {}), ('get_listening_ports', {'port': 8080})]:
            result = await client.call_tool(name, args)
            assert not result.is_error, name
            assert result.structured_content['success'], (name, result.structured_content)

@pytest.mark.parametrize('name,args', [('get_service_status', {'name': '--root=/tmp'}), ('get_package_info', {'name': 'a;id'}), ('get_listening_ports', {'port': 70000}), ('get_process_details', {'pid': -1}), ('read_journal', {'boot': 2})])
async def test_invalid_diagnostic_args(tmp_path, name, args):
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        result = await client.call_tool(name, args)
        assert not result.structured_content['success']

async def test_malformed_protocol_args(tmp_path):
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        for args in [{'port': {'nested': 'object'}}, {'port': 'bad'}, {'port': []}]:
            result = await client.call_tool('get_listening_ports', args)
            assert result.is_error
