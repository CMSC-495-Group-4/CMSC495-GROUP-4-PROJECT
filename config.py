""" Application configuration settings."""

import os
from pathlib import Path


class Config:
    """Stores shared application settings."""

    DATABASE_NAME = os.getenv("DATABASE_NAME",
        str(Path(__file__).resolve().parent / "instance" / "campuspath.db"),
    )
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    
