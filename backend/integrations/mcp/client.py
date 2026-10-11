"""Client for remote MCP servers (Streamable HTTP), on the official MCP SDK.

Agents talk to a CRM through `McpConnection`: list its tools (each one
classified read / write / blocked) and call them. Every tool result is
reduced to text for the model and treated as untrusted data by callers.
"""

import json
import re
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import ElicitResult, Implementation, Tool

ToolKind = Literal["read", "write", "blocked"]

MAX_RESULT_CHARS = 12_000
_BLOCKED_WORDS = {"delete", "remove", "purge", "destroy", "erase", "merge", "archive", "deactivate", "revoke", "wipe"}
_WRITE_WORDS = {
    "create", "update", "upsert", "add", "insert", "set", "patch", "write", "log", "assign", "move", "send",
    "convert", "manage", "batch", "edit", "change", "associate", "mass", "post", "put",
}
_READ_WORDS = {
    "get", "list", "search", "query", "find", "read", "describe", "fetch", "count", "retrieve", "lookup", "show",
    "view", "soql", "sosl", "schema", "details", "info", "recent", "related",
    # How-to and discovery tools (HubSpot's tool_guidance, discover_hubspot_schema).
    "guidance", "discover", "metadata", "help",
}
# A server asking for a confirmation it didn't get (the change wasn't made).
_NEEDS_CONFIRMATION = re.compile(
    r"please confirm|awaiting (your |user )?confirmation|requires? (an? )?(explicit )?(user )?confirmation|"
    r"confirm (to|before) (proceed|continu|execut|apply)|not (yet )?(been )?(applied|executed|made)[^.]*confirm",
    re.I,
)
# Input fields that carry a confirmation flag ("confirmed", "userConfirmed").
_CONFIRM_FIELD = re.compile(r"confirm|approv", re.I)
_SIGN_IN = re.compile(r"https://[^\s\"'<>)\]]*(?:accounts\.zoho|oauth|authori[sz]e|/auth\b|signin|sign-in|consent)[^\s\"'<>)\]]*", re.I)


class McpError(Exception):
    """A failure talking to an MCP server, with a message safe to show."""


class McpAuthError(McpError):
    """The server rejected our credentials (expired or revoked)."""


@dataclass
class McpTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    kind: ToolKind
    title: str | None = None

    def brief(self, schema_chars: int = 1500) -> dict[str, Any]:
        schema = json.dumps(self.input_schema, separators=(",", ":"), ensure_ascii=False)
        return {
            "name": self.name,
            "kind": self.kind,
            "description": " ".join(self.description.split())[:400],
            "input_schema": schema if len(schema) <= schema_chars else schema[:schema_chars] + "...(truncated)",
        }


@dataclass
class ToolOutput:
    ok: bool
    text: str
    data: Any = None
    # A sign-in link the server asked the user to open (Zoho authorises
    # each service on first use).
    sign_in_url: str | None = None


def _words(name: str) -> set[str]:
    """createSobjectRecord / search_crm_objects / MassUpdateRecords -> words."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return {w for w in re.split(r"[^a-z]+", spaced.lower()) if w}


def classify(tool: Tool) -> ToolKind:
    """Deletes and merges are never offered; reads run without asking;
    anything else that changes data needs the user's approval. Unknown
    tools count as writes, so they always need approval."""
    words = _words(tool.name)
    if words & _BLOCKED_WORDS:
        return "blocked"
    annotations = tool.annotations
    if annotations and annotations.read_only_hint is True:
        return "read"
    if annotations and annotations.read_only_hint is False:
        return "write"
    if words & _WRITE_WORDS:
        return "write"
    return "read" if words & _READ_WORDS else "write"


# Argument keys that name what a general "manage" tool should do.
_OPERATION_KEYS = {"operation", "operations", "action", "actions", "op", "method", "mode", "type", "kind", "intent", "changetype"}


def destructive_arguments(arguments: Any) -> str | None:
    """Why a write's arguments ask to delete, merge or archive records, or
    None. Some servers have one tool for every change (HubSpot's
    manage_crm_objects), so the tool's name alone can't keep deletes out."""

    def walk(value: Any, key: str = "", fields: bool = False) -> str | None:
        if isinstance(value, dict):
            for k, v in value.items():
                if not fields and _words(str(k)) & _BLOCKED_WORDS:
                    return f"it asks to {next(iter(_words(str(k)) & _BLOCKED_WORDS))} records"
                # A record's own fields ("properties") are data, like a deal type.
                found = walk(v, str(k), fields or str(k).lower() in ("properties", "fields", "values", "data"))
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = walk(item, key, fields)
                if found:
                    return found
        elif isinstance(value, str) and not fields and key.lower().replace("_", "") in _OPERATION_KEYS:
            hit = _words(value) & _BLOCKED_WORDS
            if hit:
                return f"it asks to {next(iter(hit))} records"
        return None

    return walk(arguments)


def confirmed_arguments(tool: McpTool, arguments: dict[str, Any]) -> dict[str, Any]:
    """The arguments of a change the user approved, with any yes/no
    confirmation field the tool has set to yes (some servers, like
    HubSpot's, ask for confirmation before they write)."""
    properties = (tool.input_schema or {}).get("properties") or {}
    out = dict(arguments)
    for name, spec in properties.items():
        if isinstance(spec, dict) and spec.get("type") == "boolean" and _CONFIRM_FIELD.search(name):
            out[name] = True
    return out


def asks_for_confirmation(text: str) -> bool:
    return bool(_NEEDS_CONFIRMATION.search(text or ""))


def _confirmation_answer(schema: dict[str, Any]) -> dict[str, Any] | None:
    """Answers to a server's confirmation form: yes to every yes/no field,
    the "confirm"-like choice of a list. None if the form asks for anything
    else that's required (Agentis can't make that up)."""
    required = set(schema.get("required") or [])
    answer: dict[str, Any] = {}
    for name, spec in (schema.get("properties") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        options = spec.get("enum") or [o.get("const") for o in spec.get("oneOf") or [] if isinstance(o, dict)]
        if spec.get("type") == "boolean":
            answer[name] = True
        elif options and (choice := next((o for o in options if re.match(r"(yes|confirm|approve|proceed|accept|ok)", str(o), re.I)), None)):
            answer[name] = choice
        elif name in required:
            return None
    return answer


class _Approval:
    """Whether the call in flight is a change the user approved; only then
    are a server's confirmation requests (MCP elicitation) answered yes."""

    def __init__(self) -> None:
        self.approved = False

    async def __call__(self, context: Any, params: Any) -> ElicitResult:
        if not self.approved or getattr(params, "mode", "form") == "url":
            return ElicitResult(action="decline")
        answer = _confirmation_answer(getattr(params, "requested_schema", None) or {})
        return ElicitResult(action="accept", content=answer) if answer is not None else ElicitResult(action="decline")


def _to_tool(tool: Tool) -> McpTool:
    return McpTool(
        name=tool.name,
        description=tool.description or tool.title or "",
        input_schema=tool.input_schema or {"type": "object"},
        kind=classify(tool),
        title=tool.title,
    )


def _text_of(result: Any) -> str:
    parts = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
        elif getattr(item, "uri", None):
            parts.append(f"[resource {item.uri}]")
        else:
            parts.append(f"[{getattr(item, 'type', 'content')}]")
    if not parts and getattr(result, "structured_content", None) is not None:
        parts.append(json.dumps(result.structured_content, ensure_ascii=False, default=str))
    return "\n".join(parts)


def _unwrap(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (httpx2.HTTPError, MCPError, TimeoutError, OSError, anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream)


def _mapped(exc: BaseException, server: str, statuses: list[int]) -> BaseException:
    """Transport failures become McpError (McpAuthError for 401/403);
    anything else (including McpError raised by callers) passes through."""
    inner = _unwrap(exc)
    if isinstance(inner, McpError):
        return inner
    if any(s in (401, 403) for s in statuses):
        return McpAuthError(f"{server} rejected the connection; reconnect it on the Connect page")
    if not isinstance(inner, _TRANSPORT_ERRORS):
        return inner
    if isinstance(inner, (httpx2.TimeoutException, TimeoutError)):
        return McpError(f"{server} took too long to answer")
    status = next((s for s in reversed(statuses) if s >= 400), None)
    if status:
        return McpError(f"{server} answered with an error (HTTP {status})")
    if isinstance(inner, MCPError):
        return McpError(f"{server} returned an error: {inner}")
    return McpError(f"Couldn't reach {server}")


class McpConnection:
    """One open MCP session. Use `open_connection` to create it."""

    def __init__(self, session: ClientSession, server: str, statuses: list[int] | None = None, approval: _Approval | None = None):
        self._session = session
        self.server = server
        self._statuses = statuses if statuses is not None else []
        self._tools: list[McpTool] | None = None
        self._approval = approval or _Approval()

    async def tools(self) -> list[McpTool]:
        if self._tools is None:
            tools: list[McpTool] = []
            cursor = None
            try:
                for _ in range(20):
                    page = await self._session.list_tools(params={"cursor": cursor} if cursor else None)
                    tools.extend(_to_tool(t) for t in page.tools)
                    cursor = page.next_cursor
                    if not cursor:
                        break
            except Exception as exc:  # noqa: BLE001 - mapped below
                raise _mapped(exc, self.server, self._statuses) from exc
            self._tools = tools
        return self._tools

    async def tool(self, name: str) -> McpTool | None:
        return next((t for t in await self.tools() if t.name == name), None)

    async def call(self, name: str, arguments: dict[str, Any], timeout: float = 45.0, *, approved: bool = False) -> ToolOutput:
        """Runs a tool. `approved` is for a change the user approved: the
        server's own confirmation requests during it are answered yes."""
        self._approval.approved = approved
        try:
            result = await self._session.call_tool(name, arguments, read_timeout_seconds=timeout)
        except Exception as exc:  # noqa: BLE001 - mapped below
            raise _mapped(exc, self.server, self._statuses) from exc
        finally:
            self._approval.approved = False
        text = _text_of(result)
        data = getattr(result, "structured_content", None)
        if data is None:
            try:
                data = json.loads(text) if text.strip()[:1] in ("{", "[") else None
            except ValueError:
                data = None
        failed = bool(getattr(result, "is_error", False))
        sign_in = None
        if failed or re.search(r"authori[sz]|sign.?in|connect your", text, re.I):
            match = _SIGN_IN.search(text)
            sign_in = match.group(0) if match else None
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + f"\n...(cut, {len(text) - MAX_RESULT_CHARS} more characters)"
        return ToolOutput(ok=not failed, text=text, data=data, sign_in_url=sign_in)


@asynccontextmanager
async def open_connection(url: str, *, bearer: str | None = None, server: str = "The MCP server", timeout: float = 30.0) -> AsyncIterator[McpConnection]:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    statuses: list[int] = []

    async def record(response: httpx2.Response) -> None:
        statuses.append(response.status_code)

    try:
        async with AsyncExitStack() as stack:
            http = create_mcp_http_client(headers=headers, timeout=httpx2.Timeout(timeout, read=90.0))
            http.event_hooks["response"].append(record)
            await stack.enter_async_context(http)
            streams = await stack.enter_async_context(streamable_http_client(url, http_client=http))
            approval = _Approval()
            session = await stack.enter_async_context(
                ClientSession(
                    streams[0], streams[1], client_info=Implementation(name="Agentis", version="1.0"), elicitation_callback=approval
                )
            )
            await session.initialize()
            yield McpConnection(session, server, statuses, approval)
    except Exception as exc:  # noqa: BLE001 - the SDK wraps failures in task-group exception groups
        raise _mapped(exc, server, statuses) from exc
