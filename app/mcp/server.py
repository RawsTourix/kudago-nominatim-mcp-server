from fastmcp import FastMCP

from app.mcp.tools import register_geo_tools


mcp = FastMCP("kudago-nominatim")
register_geo_tools(mcp)


def create_mcp_server() -> FastMCP:
    return mcp
