from .base import *

DEBUG = True

# WhiteNoise serves the collectstatic output, which only exists in the built
# image. runserver serves static files itself while DEBUG is True, so drop the
# middleware here to avoid a "No directory at: .../staticfiles/" warning.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

# The manifest is produced by collectstatic during the image build and does
# not exist here, so {% static %} would raise "Missing staticfiles manifest
# entry" while rendering any admin page.
STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
