from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance. Imported by main.py to register the exception
# handler and by individual routes to apply per-route limits (e.g. the
# unauthenticated citizen tracking-id lookup, which needs throttling against
# enumeration).
limiter = Limiter(key_func=get_remote_address)
