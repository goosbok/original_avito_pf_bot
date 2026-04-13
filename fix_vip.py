import sqlite3
from data import config
from data.config import path_database as path_db
from utils.sqlite3 import all_users, update_user

users = all_users()
for user in users:
    if user['is_vip'] is not None:
        if int(user['is_vip']) == 0:
            update_user(id=user['id'], is_vip=None)