"""
H-Bit Identity Registry (Local Prototype)
-----------------------------------------

Sistema de base de datos local para vincular hashes criptográficos de autor
con identidades del mundo real (Nombre, Email, Organización).

Esquema:
    - identities:
        - author_hash (PRIMARY KEY, TEXT)
        - name (TEXT)
        - email (TEXT)
        - organization (TEXT)
        - public_key (TEXT)
        - registered_at (DATETIME)
        - verified (BOOLEAN)

Uso:
    registry = IdentityRegistry("apps/hbfs/data/identity.db")
    registry.register("hash123", "Juan Perez", "jperez@email.com")
    info = registry.lookup("hash123")
"""

import sqlite3
import datetime
from pathlib import Path
from typing import Optional, Dict

class IdentityRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Inicializa la base de datos si no existe."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS identities (
                author_hash TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                organization TEXT,
                public_key TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified BOOLEAN DEFAULT 0
            )
        ''')
        conn.commit()
        conn.close()

    def register(self, author_hash: str, name: str, email: str = "", organization: str = "", public_key: str = "") -> bool:
        """Registra una nueva identidad (o actualiza existente)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO identities (author_hash, name, email, organization, public_key, verified)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (author_hash, name, email, organization, public_key))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error registering identity: {e}")
            return False

    def lookup(self, author_hash: str) -> Optional[Dict[str, str]]:
        """Busca una identidad por hash."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM identities WHERE author_hash = ?', (author_hash,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(row)
            return None
        except Exception as e:
            print(f"Error lookup identity: {e}")
            return None

    def list_all(self):
        """Lista todas las identidades registradas."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM identities')
            rows = cursor.fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []
