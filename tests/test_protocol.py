from mcp import Client

from cachyos_mcp.config import PROJECT, Settings
from cachyos_mcp.server import create_server


async def test_initialization_and_system_tools(tmp_path):
    server = create_server(Settings(log_directory=str(tmp_path)))
    async with Client(server) as client:
        tools = await client.list_tools()
        assert any(t.name == "get_system_info" for t in tools.tools)
        result = await client.call_tool("get_memory_info")
        assert not result.is_error
        assert result.structured_content["data"]["total"] > 0
        result = await client.call_tool("get_system_info")
        assert result.structured_content["data"]["os"]["ID"] == "cachyos"


async def test_real_stdio():
    from mcp import StdioServerParameters

    async with Client(StdioServerParameters(command=str(PROJECT / "scripts/launch.sh"))) as client:
        result = await client.call_tool("get_kernel_info")
        assert result.structured_content["success"]
        assert "cachyos" in result.structured_content["data"]["release"]


async def test_strict_inputs_and_disabled_groups(tmp_path):
    async with Client(create_server(Settings(log_directory=str(tmp_path)))) as client:
        for name, args in [
            ("get_listening_ports", {"port": True}),
            ("get_listening_ports", {"port": "8080"}),
            ("get_memory_info", {"extra": "secret-value"}),
            ("create_file", {"path": "/tmp/file", "content": "hello"}),
        ]:
            result = await client.call_tool(name, args)
            assert result.is_error
    assert "secret-value" not in (tmp_path / "audit.jsonl").read_text()
    async with Client(
        create_server(Settings(log_directory=str(tmp_path), enabled_tool_groups=["system"]))
    ) as client:
        listed = await client.list_tools()
        assert all(t.name.startswith("get_") for t in listed.tools)
        assert not any(t.name == "install_package" for t in listed.tools)


async def test_user_change_permission_gate(tmp_path):
    async with Client(
        create_server(Settings(log_directory=str(tmp_path), user_changes_enabled=False))
    ) as client:
        result = await client.list_tools()
        names = {tool.name for tool in result.tools}
        assert "inspect_path" in names
        assert "get_service_status" in names
        assert "create_file" not in names
        assert "create_systemd_user_service" not in names
        assert "git_commit" not in names
        result = await client.call_tool("install_package", {"name": "blender", "confirmed": True})
        assert not result.structured_content["success"]
