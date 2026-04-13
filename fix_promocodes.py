#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      UB8CLB
#
# Created:     28.05.2024
# Copyright:   (c) UB8CLB 2024
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import sqlite3
from utils.sqlite3 import all_users, update_promocode, all_promocodes
from data import config
from data.config import path_database as path_db

conn = sqlite3.connect(path_db)
conn.row_factory = lambda cursor, row: row[0]

def main():
    users = all_users()
    promocodes = all_promocodes()
    for promocode in promocodes:
        if promocode['prom_users']:
            for user in users:
                if str(user['id']) in promocode['prom_users']:
                    promocode['prom_users'] = promocode['prom_users'].replace(str(user['id']), f",{str(user['id'])},").replace(',,', ',')
            if promocode['prom_users'][:1] == ",":
                promocode['prom_users'] = promocode['prom_users'][1:]
            len_pr_users = len(promocode['prom_users']) - 1
            if promocode['prom_users'][len_pr_users:] == ",":
                promocode['prom_users'] = promocode['prom_users'][:len_pr_users]
            users_str = promocode['prom_users']
            update_promocode(increment=promocode['increment'], prom_users=users_str)
    promocodes = all_promocodes()
    print(promocodes)

if __name__ == '__main__':
    main()
