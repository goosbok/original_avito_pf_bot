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


class AccountMergeConflict(ServiceError):
    """Phone-provider is already linked to a different user with non-empty
    provider set (full account, not phone-only).

    Raised by `identity.link_phone_provider()` when a phone number is occupied
    by an established user — caller must direct the actor to support for manual
    merge instead of silently overwriting.
    """

    def __init__(self, existing_user_id: int, target_user_id: int, phone: str) -> None:
        super().__init__(
            f"phone {phone} занят user_id={existing_user_id}, "
            f"нельзя привязать к user_id={target_user_id}"
        )
        self.existing_user_id = existing_user_id
        self.target_user_id = target_user_id
        self.phone = phone


class OrderNotFound(ServiceError):
    """Order with the requested id does not exist (or belongs to another user
    in scoped lookups)."""


class OrderStatusConflict(ServiceError):
    """Attempted state transition is illegal for the order's current status.

    Examples: paying an already-paid order, cancelling a done order, etc.
    Callers translate to HTTP 409 / a user-facing nudge.
    """


class PaymentExpired(ServiceError):
    """Attempted to pay an `unpaid` order whose `payment_expires_at` has passed.

    Caller should refuse the payment and prompt the actor to create a new order.
    """


class LinkNotFound(ServiceError):
    """Ссылка order_links с переданным id не найдена."""


class InvalidLinkTransition(ServiceError):
    """Попытка изменить статус ссылки на недопустимый.

    Например, in_work → in_work (no-op обрабатывается выше),
    или done → in_work (terminal).
    """

    def __init__(self, *, from_status: str, to_status: str) -> None:
        super().__init__(
            f"Invalid link transition: {from_status} → {to_status}"
        )
        self.from_status = from_status
        self.to_status = to_status


class ExecutorAPIError(ServiceError):
    """Ошибка при работе с API исполнителя ПФ."""


class ExecutorAPIRejected(ExecutorAPIError):
    """API явно отказался брать ссылку (не поддерживает регион/тип/и т.п.).

    Caller должен fallback'нуться в manual delivery_mode.
    Отличается от `ExecutorAPIError` тем, что повторная попытка не поможет.
    """


class NothingToWithdraw(ServiceError):
    """Попытка вывести реферальный баланс, когда он равен нулю."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"user_id={user_id}: referral_balance is 0, nothing to withdraw")
        self.user_id = user_id


class WithdrawConflict(ServiceError):
    """referral_balance изменился между чтением и записью (гонка с новым бонусом)."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"user_id={user_id}: referral_balance changed concurrently, retry")
        self.user_id = user_id
