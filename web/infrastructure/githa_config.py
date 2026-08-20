"""
Githa Database Configuration — PipelineFace
============================================
Parâmetros de conexão com o banco de dados PostgreSQL do projeto Githa.
"""

import os
from typing import Dict, Any


def get_githa_db_config() -> Dict[str, Any]:
    return {
        "host": os.environ.get("GITHA_DB_HOST", "localhost"),
        "port": int(os.environ.get("GITHA_DB_PORT", "5432")),
        "dbname": os.environ.get("GITHA_DB_NAME", "githa"),
        "user": os.environ.get("GITHA_DB_USER", "postgres"),
        "password": os.environ.get("GITHA_DB_PASSWORD", "postgres"),
        "connect_timeout": 3
    }
