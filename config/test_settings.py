from .settings import *  # noqa: F401,F403

   # Tests run on a throwaway in-memory SQLite database, never on Neon.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}