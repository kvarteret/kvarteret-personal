import os


# Runtime configuration is intentionally explicit. Tests use the safe, non-deployed
# environment unless an individual test supplies another value.
os.environ.setdefault("APP_ENV", "test")
