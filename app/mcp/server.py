from fastmcp import FastMCP
from fastmcp.server.lifespan import lifespan

from app.core.config import Settings, settings
from app.core.redis import close_arq_pool, create_arq_pool
from app.mcp.tools import (
    register_cinema_tools,
    register_content_tools,
    register_details_tools,
    register_discovery_tools,
    register_routing_tools,
)


def create_mcp_server(*, settings_obj: Settings = settings) -> FastMCP:
    @lifespan
    async def mcp_lifespan(server):
        redis = await create_arq_pool(settings_obj.redis_url)
        try:
            yield {"arq_redis": redis}
        finally:
            await close_arq_pool(redis)

    server = FastMCP("kudago-nominatim", lifespan=mcp_lifespan)
    register_discovery_tools(server)
    register_cinema_tools(server)
    register_content_tools(server)
    register_details_tools(server)
    register_routing_tools(server, settings_obj=settings_obj)
    return server


mcp = create_mcp_server()
