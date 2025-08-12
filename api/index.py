from app import app

# Initialize database on first run
from database import init_database
init_database()

if __name__ == "__main__":
    app.run()