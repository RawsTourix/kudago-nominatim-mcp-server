from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP


def create_mcp_server() -> "FastMCP":
    from .server import create_mcp_server as factory

    return factory()


def __getattr__(name: str) -> Any:
    if name == "mcp":
        from .server import mcp

        return mcp
    raise AttributeError(name)


__all__ = ["create_mcp_server", "mcp"]
