from .base import *

DEBUG = True

# WhiteNoise serves the collectstatic output, which only exists in the built
# image. runserver serves static files itself while DEBUG is True, so drop the
# middleware here to avoid a "No directory at: .../staticfiles/" warning.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]
