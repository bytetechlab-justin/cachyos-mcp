import inspect
import time
from contextvars import ContextVar
from functools import wraps

from mcp.types import CallToolResult, TextContent, ToolAnnotations
from mcp_types.methods import serialize_server_result
from pydantic import TypeAdapter, ValidationError

from .executor import Executor
from .logging_config import Audit
from .security import Denied, Paths

# Only these validated scalar argument fields are suitable for audit logs.
CURRENT_TOOL = ContextVar("current_tool", default=(None, 0))

AUDIT_FIELDS = {"pid", "limit", "port", "confirmed", "user", "boot", "priority", "action"}


class Runtime:
    def __init__(self, settings, server):
        self.settings = settings
        self.server = server
        self.executor = Executor(settings)
        self.paths = Paths(settings)
        self.audit = Audit(settings)
        self.signatures = {}

    def tool(self, group, level=1):
        def decorate(fn):
            if group not in self.settings.enabled_tool_groups:
                return fn

            self.signatures[fn.__name__] = (inspect.signature(fn), level)

            @wraps(fn)
            async def wrapped(*args, **kwargs):
                started = time.monotonic()
                bound = inspect.signature(fn).bind(*args, **kwargs)
                sanitized = {
                    k: v if k in AUDIT_FIELDS and isinstance(v, (bool, int)) else "[redacted]"
                    for k, v in bound.arguments.items()
                }
                # Write an intent event before any side effects; fail closed on audit failure.
                self.audit.record(
                    tool=fn.__name__, arguments=sanitized, permission_level=level, event="start"
                )
                try:
                    value = fn(*args, **kwargs)
                    result = await value if inspect.isawaitable(value) else value
                    if "success" not in result:
                        result = {"success": True, "data": result}
                except (Denied, ValueError, OSError) as exc:
                    result = {
                        "success": False,
                        "error": type(exc).__name__,
                        "message": str(exc)
                        if isinstance(exc, Denied)
                        else "Invalid input or unavailable resource",
                    }
                self.audit.record(
                    tool=fn.__name__,
                    arguments=sanitized,
                    permission_level=level,
                    command=self.safe_command(result.get("command")),
                    success=result["success"],
                    exit_code=result.get("exit_code"),
                    duration_ms=round((time.monotonic() - started) * 1000),
                    event="finish",
                )
                return result

            self.server.tool(
                annotations=ToolAnnotations(
                    readOnlyHint=level == 1, destructiveHint=level > 1, openWorldHint=False
                ),
                structured_output=True,
            )(wrapped)
            return wrapped

        return decorate

    @staticmethod
    def safe_command(command):
        # Preserve executable and fixed flags; redact externally supplied values.
        if not command:
            return None
        return [
            command[0],
            *[
                arg
                if arg
                in {
                    "--no-pager",
                    "--user",
                    "--needed",
                    "--noconfirm",
                    "--noprogressbar",
                    "--json",
                    "--no-ext-diff",
                    "--no-textconv",
                    "--literal-pathspecs",
                }
                else "[argument]"
                for arg in command[1:]
            ],
        ]

    async def run(self, argv, **kwargs):
        result = await self.executor.run(argv, **kwargs)
        self.audit.record(
            event="command",
            tool=CURRENT_TOOL.get()[0],
            permission_level=CURRENT_TOOL.get()[1],
            command=self.safe_command(argv),
            success=result["success"],
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
        )
        return result

    async def middleware(self, ctx, call_next):
        """Audit and validate raw MCP tool arguments before SDK coercion or dispatch."""
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params if isinstance(ctx.params, dict) else {}
        name = params.get("name")
        registered = self.signatures.get(name) if isinstance(name, str) else None
        safe_name = name if registered else "[unknown]"
        level = registered[1] if registered else 0
        token = CURRENT_TOOL.set((safe_name, level))
        self.audit.record(tool=safe_name, permission_level=level, event="request")
        try:
            if registered:
                try:
                    arguments = params.get("arguments", {})
                    if not isinstance(arguments, dict):
                        raise TypeError("Expected object")
                    bound = registered[0].bind(**arguments)
                    for key, value in bound.arguments.items():
                        annotation = registered[0].parameters[key].annotation
                        TypeAdapter(annotation).validate_python(value, strict=True)
                except (TypeError, ValueError, ValidationError):
                    self.audit.record(
                        tool=safe_name,
                        permission_level=level,
                        event="rejected",
                        success=False,
                        error="invalid_arguments",
                    )
                    result = CallToolResult(
                        is_error=True,
                        content=[
                            TextContent(
                                type="text",
                                text="Invalid arguments: use the published schema, exact JSON types, required fields, and no extra fields.",
                            )
                        ],
                        structured_content={"success": False, "error": "invalid_arguments"},
                    )
                    return serialize_server_result(
                        "tools/call",
                        ctx.protocol_version,
                        result.model_dump(by_alias=True, mode="json", exclude_none=True),
                    )
            return await call_next(ctx)
        except BaseException:
            self.audit.record(
                tool=safe_name, permission_level=level, event="request_failed", success=False
            )
            raise
        finally:
            CURRENT_TOOL.reset(token)
