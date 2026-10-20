import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["ADMIN_PASSWORD"] = "admin-test-pass"
if os.path.exists("test.db"):
    os.remove("test.db")
