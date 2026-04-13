import asyncio
import json
import os
import uuid

from data.config import SHOP_ID, SECRET_KEY, botlink
from yookassa import Configuration, Payment

"""
SHOP_ID = os.getenv("SHOP_ID")
SECRET_KEY = os.getenv("SECRET_KEY")
SUB_AMOUNT = os.getenv("SUB_AMOUNT")
URL_BOT = os.getenv("URL_BOT")
"""
URL_BOT = botlink



def create_invoice(user_id, AMOUNT):

    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY
    print(user_id)
    
    # Add receipt information
    receipt = {
        "items": [
            {
                "description": f"Пополнение баланса {user_id}",
                "quantity": 1,
                "amount": {
                    "value": f"{AMOUNT}.00",
                    "currency": "RUB"
                },
                "vat_code": 1,
                "payment_mode": "full_prepayment",
                "payment_subject": "commodity"
            }
        ],
        "tax_system_code": 1,
        "email": "user@example.com"
    }

    payment = Payment.create({
        "amount": {
            "value": f"{AMOUNT}.00",
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": f"{URL_BOT}"
        },
        "receipt": receipt,
        "capture": True,
        "description": f"Пполнение баланса {user_id}"
    }, str(uuid.uuid4()))  # Generate a random ID for the payment

    payment_data = json.loads(payment.json())
    payment_id = payment_data['id']
    payment_url = payment_data['confirmation']['confirmation_url']
    print(payment_id)
    return payment_url, payment_id


async def check_payment_status(payment_id):
    Configuration.account_id = SHOP_ID
    Configuration.secret_key = SECRET_KEY

    max_attempts = 12  # 12 попыток с задержкой в 30 секунд
    attempts = 0

    while attempts < max_attempts:
        payment_response = Payment.find_one(payment_id)
        print(payment_response.status)

        if payment_response.status == "succeeded":
            return True
        elif payment_response.status in ["canceled", "expired", "rejected"]:
            return False
        elif payment_response.status == "waiting_for_capture":
            # Вызов метода "Capture" для завершения платежа
            captured_payment = Payment.capture(payment_id)
            print(captured_payment.status)

            if captured_payment.status == "succeeded":
                return True
            else:
                return False

        attempts += 1
        await asyncio.sleep(30)

    return False  # Статус платежа не обновлен после максимального числа попыток