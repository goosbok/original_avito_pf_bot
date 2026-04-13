import sqlite3
from data import config
from data.config import path_database as path_db

conn = sqlite3.connect(path_db)
conn.row_factory = lambda cursor, row: row[0]
c = conn.cursor()
c.execute('ALTER TABLE orders ADD contacts BOOLEN DEFAULT False')