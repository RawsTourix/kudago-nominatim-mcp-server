from fastmcp import FastMCP

from app.core.config import Settings, settings
from app.mcp.tools import (
    register_cinema_tools,
    register_content_tools,
    register_details_tools,
    register_discovery_tools,
    register_routing_tools,
)


def create_mcp_server(*, settings_obj: Settings = settings) -> FastMCP:
    server = FastMCP("kudago-nominatim")
    register_discovery_tools(server)
    register_cinema_tools(server)
    register_content_tools(server)
    register_details_tools(server)
    register_routing_tools(server, settings_obj=settings_obj)
    return server


mcp = create_mcp_server()
