import os


def prepare_stdio_environment() -> None:
    # SQLAlchemy's echo handler writes to stdout, which would corrupt the
    # newline-delimited JSON-RPC stream used by MCP stdio transport.
    os.environ["DATABASE_ECHO"] = "0"


def main() -> None:
    prepare_stdio_environment()

    # Import only after the stdio-safe environment is established because
    # importing app.core.db creates the SQLAlchemy engine immediately.
    from app.mcp.server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
