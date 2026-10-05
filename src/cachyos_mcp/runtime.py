from functools import wraps
import inspect
import time
from mcp.types import ToolAnnotations
from .security import Denied, Paths
from .executor import Executor
from .logging_config import Audit

# Only these validated scalar argument fields are suitable for audit logs.
AUDIT_FIELDS = {'pid', 'limit', 'port', 'confirmed', 'user', 'boot', 'priority', 'action'}

class Runtime:
    def __init__(self, settings, server):
        self.settings = settings
        self.server = server
        self.executor = Executor(settings)
        self.paths = Paths(settings)
        self.audit = Audit(settings)

    def tool(self, group, level=1):
        def decorate(fn):
            if group not in self.settings.enabled_tool_groups:
                return fn
            @wraps(fn)
            async def wrapped(*args, **kwargs):
                started = time.monotonic()
                bound = inspect.signature(fn).bind(*args, **kwargs)
                sanitized = {k: v for k, v in bound.arguments.items() if k in AUDIT_FIELDS and isinstance(v, (bool, int))}
                # Write an intent event before any side effects; fail closed on audit failure.
                self.audit.record(tool=fn.__name__, arguments=sanitized, permission_level=level, event='start')
                try:
                    value = fn(*args, **kwargs)
                    result = await value if inspect.isawaitable(value) else value
                    if 'success' not in result:
                        result = {'success': True, 'data': result}
                except (Denied, ValueError, OSError) as exc:
                    result = {'success': False, 'error': type(exc).__name__, 'message': str(exc) if isinstance(exc, Denied) else 'Invalid input or unavailable resource'}
                self.audit.record(tool=fn.__name__, arguments=sanitized, permission_level=level,
                                  command=self.safe_command(result.get('command')), success=result['success'],
                                  exit_code=result.get('exit_code'), duration_ms=round((time.monotonic()-started)*1000), event='finish')
                return result
            self.server.tool(annotations=ToolAnnotations(readOnlyHint=level == 1, destructiveHint=level > 1, openWorldHint=False), structured_output=True)(wrapped)
            return wrapped
        return decorate

    @staticmethod
    def safe_command(command):
        # Preserve executable and fixed flags; redact externally supplied values.
        if not command:
            return None
        return [command[0], *[arg if arg.startswith('--') and '=' not in arg else '[argument]' for arg in command[1:]]]

    async def run(self, argv, **kwargs):
        return await self.executor.run(argv, **kwargs)
