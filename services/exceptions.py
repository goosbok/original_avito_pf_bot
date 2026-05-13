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


class InvalidCredentials(ServiceError):
    """Email + password не совпадают, или provider/identifier не найден."""


class ProviderAlreadyLinked(ServiceError):
    """Пытаются привязать identifier, который уже привязан к другому user_id."""

    def __init__(self, provider: str, identifier: str, existing_user_id: int):
        super().__init__(f"{provider}:{identifier} already linked to user {existing_user_id}")
        self.provider = provider
        self.identifier = identifier
        self.existing_user_id = existing_user_id


class OTPInvalid(ServiceError):
    """Код не совпадает или превышен лимит попыток."""


class OTPExpired(ServiceError):
    """Срок жизни кода истёк."""


class OTPCooldown(ServiceError):
    """Слишком частые запросы кода."""

    def __init__(self, retry_after_seconds: int):
        super().__init__(f"Try again in {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


class ApplicationNotFound(ServiceError):
    pass


class InvalidAPIKey(ServiceError):
    pass


class EmailAlreadyRegistered(ServiceError):
    pass


class BotCantReachUser(ServiceError):
    """Telegram bot could not deliver a message to the user.

    Typical causes: user never started the bot, or has blocked it.
    This is a user-actionable error, not a server failure.
    """


class EmailSendError(ServiceError):
    """SMTP send failed."""
