import os

from app import create_app
from config.config import config_by_name

env = os.environ.get("FLASK_ENV", "development")
config_class = config_by_name.get(env, config_by_name["development"])
app = create_app(f"config.config.{config_class.__name__}")

if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
