#!/usr/bin/python

#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      KIPiA
#
# Created:     06.01.2025
# Copyright:   (c) KIPiA 2025
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import sqlite3
from data.config import path_database as path_db
from utils.sqlite3 import all_orders
from datetime import date, datetime
from data.loader import bot
import asyncio

async def main():
    orders = all_orders()
    d0 = datetime.now()
    for order in orders:
        days_in_order = int(order['position_name'].split('/')[0])
        d1 = datetime.strptime(order['date'], '%d.%m.%Y %H:%M:%S')
        delta = d0 - d1
        if order['status'] == 'Posted':
            if delta.days >= days_in_order:
                status = 'Completed'
                with sqlite3.connect(path_db) as con:
                    sql = "UPDATE orders SET status = ? WHERE increment = ?"
                    con.execute(sql, (status, order['increment']))
                    con.commit()
                msg = f"✅ Ваш заказ №<code>{order['increment']}</code> на накрутку ПФ выполнен."
                try:
                    await bot.send_message(chat_id=int(order['user_id']), text=msg, disable_web_page_preview=True)
                except Exception as e:
                    pass

if __name__ == '__main__':
    asyncio.run(main())
