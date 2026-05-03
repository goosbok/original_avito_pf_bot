"""Общие исключения сервисного слоя.

Сервисы бросают эти исключения, а вызывающий код (бот / FastAPI) превращает их
в человеко-читаемые сообщения / HTTP-ответы.
"""


class ServiceError(Exception):
    """Базовое исключение сервисного слоя."""


class UserNotFound(ServiceError):
    """Пользователя с переданным id нет в БД."""


class InsufficientBalance(ServiceError):
    """Баланс пользователя меньше требуемой суммы."""

    def __init__(self, user_id: int, available: int, required: int) -> None:
        super().__init__(
            f"User {user_id}: balance {available} < required {required}"
        )
        self.user_id = user_id
        self.available = available
        self.required = required


class PaymentError(ServiceError):
    """Ошибка при работе с провайдером платежей (yookassa)."""
