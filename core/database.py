
from contextlib import contextmanager
from pathlib import Path
import sqlite3


PROJECT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_DIR / "brightloop.db"


class DatabaseManager:
    def __init__(self, db_path=DB_PATH):
        self.db_path = Path(db_path)

    def get_connection(self):
        """Create a configured SQLite connection."""

        connection = sqlite3.connect(
            self.db_path,
            timeout=5.0
        )

        connection.row_factory = sqlite3.Row

        # Enable foreign-key enforcement
        connection.execute("PRAGMA foreign_keys = ON")

        # Configure busy timeout
        connection.execute("PRAGMA busy_timeout = 5000")

        return connection

    def initialize(self):
        """Initialize the database and configure WAL mode."""

        connection = self.get_connection()

        try:
            connection.execute("PRAGMA journal_mode = WAL")

            schema_path = Path(__file__).resolve().parent / "schema.sql"
            schema = schema_path.read_text(encoding="utf-8")

            connection.executescript(schema)

            print("Brightloop database initialized successfully.")

        finally:
            connection.close()

    @contextmanager
    def transaction(self):
        """Run database operations in an atomic transaction."""

        connection = self.get_connection()

        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()


if __name__ == "__main__":
    db = DatabaseManager()
    db.initialize()
