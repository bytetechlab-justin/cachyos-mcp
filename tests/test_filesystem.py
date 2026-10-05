from pathlib import Path
import os
import pytest
from mcp import Client
from cachyos_mcp.config import Settings, PROJECT
from cachyos_mcp.security import Paths, Denied
from cachyos_mcp.server import create_server

@pytest.fixture
def paths(tmp_path):
    settings = Settings().model_copy(update={'allowed_writable_directories': [str(tmp_path)], 'allowed_project_directories': [str(tmp_path)]})
    # /tmp is a test-only root; production Settings rejects it.
    return Paths(settings)

@pytest.mark.parametrize('value', ['/etc/passwd', '/root/x', '/usr/bin/x', '~/Projects/../.ssh/id_rsa', '~/.config/../.codex/config.toml', str(PROJECT / 'config/settings.toml'), '~/.config/keyrings/key', '~/.local/share/foo/token.txt'])
def test_blocked_write(paths, value):
    with pytest.raises(Denied):
        paths.checked(value, write=True)

def test_allowed_write_and_backup(paths, tmp_path):
    p = tmp_path / 'example.txt'
    paths.write(str(p), 'first')
    result = paths.write(str(p), 'second', replace=True)
    assert p.read_text() == 'second'
    assert Path(result['backup']).read_text() == 'first'
    assert p.stat().st_mode & 0o077 == 0

def test_no_overwrite(paths, tmp_path):
    p = tmp_path / 'file'
    paths.write(str(p), 'first')
    with pytest.raises(FileExistsError):
        paths.write(str(p), 'second')
    assert p.read_text() == 'first'

@pytest.mark.parametrize('replace', [False, True])
def test_parent_symlink(paths, tmp_path, replace):
    (tmp_path / 'escape').symlink_to('/tmp')
    with pytest.raises(OSError):
        paths.write(str(tmp_path / 'escape' / 'escape-test'), 'blocked', replace=replace)

def test_leaf_symlink(paths, tmp_path):
    target = tmp_path / 'target'
    target.write_text('safe')
    link = tmp_path / 'link'
    link.symlink_to(target)
    with pytest.raises(OSError):
        paths.write(str(link), 'changed', replace=True)
    assert target.read_text() == 'safe'

def test_hardlink(paths, tmp_path):
    target = tmp_path / 'target'
    target.write_text('safe')
    link = tmp_path / 'hardlink'
    os.link(target, link)
    with pytest.raises(Denied):
        paths.write(str(link), 'changed', replace=True)
    assert target.read_text() == 'safe'

def test_oversized_write(paths, tmp_path):
    with pytest.raises(Denied):
        paths.write(str(tmp_path / 'large'), 'a' * (paths.settings.max_file_size + 1))

def test_sibling_prefix(paths, tmp_path):
    with pytest.raises(Denied):
        paths.checked(str(tmp_path.with_name(tmp_path.name + '-evil') / 'file'), write=True)

async def test_confirmation_and_audit(tmp_path):
    settings = Settings(log_directory=str(tmp_path / 'logs')).model_copy(update={'allowed_writable_directories': [str(tmp_path)]})
    async with Client(create_server(settings)) as client:
        args = {'path': str(tmp_path / 'created'), 'content': 'MY_SECRET_CONTENT', 'confirmed': False}
        result = await client.call_tool('create_file', args)
        assert not result.structured_content['success']
        args['confirmed'] = 'true'
        result = await client.call_tool('create_file', args)
        assert result.is_error
        args['confirmed'] = True
        result = await client.call_tool('create_file', args)
        assert result.structured_content['success']
    assert 'MY_SECRET_CONTENT' not in (tmp_path / 'logs/audit.jsonl').read_text()
