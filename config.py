"""Application configuration settings."""

import os


class Config:
    """Stores shared application settings."""

    DATABASE_NAME = os.getenv("DATABASE_NAME", "campuspath.db")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    