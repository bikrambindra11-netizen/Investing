import os
import tempfile

# Must be set before the app is imported: temp database, no network jobs.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["RUN_JOBS"] = "false"
os.environ["UPSTOX_API_KEY"] = ""
os.environ["UPSTOX_API_SECRET"] = ""
os.environ["UPSTOX_ACCESS_TOKEN"] = ""
