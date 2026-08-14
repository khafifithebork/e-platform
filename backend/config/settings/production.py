"""Production settings.

DEBUG is assigned literally rather than read from the environment. A typo in a
platform environment variable must not be able to switch it on, and there is no
legitimate reason to run production with it enabled.
"""

from .base import *

DEBUG = False

# ---------------------------------------------------------------------------
# Transport security
#
# SECURE_PROXY_SSL_HEADER is required because TLS terminates at the edge
# (Cloudflare) and the origin sees plain HTTP. Without it Django believes every
# request is insecure and SECURE_SSL_REDIRECT causes a redirect loop.
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000  # one year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

X_FRAME_OPTIONS = "DENY"
