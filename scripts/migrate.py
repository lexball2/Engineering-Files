"""Run database migrations once before API replicas start."""
from backend.database import init_db


if __name__ == "__main__":
    init_db()
    print("Database migration completed")
