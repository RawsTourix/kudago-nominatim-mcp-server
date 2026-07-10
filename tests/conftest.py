import os


os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/kudago",
)
os.environ.setdefault(
    "TRANSITOUS_USER_AGENT",
    "kudago-nominatim-tests/0.1.0 tests@example.com",
)
os.environ.setdefault(
    "OPENROUTESERVICE_USER_AGENT",
    "kudago-nominatim-tests/0.1.0",
)
