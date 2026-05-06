"""API-key authentication for third-party apps.

Каждый запрос требует:
- X-API-Key: <ключ>
- X-End-User-Id: <идентификатор end-user в стороннем приложении>

Мы создаём (или находим) внутреннего юзера с auth_provider(provider='api:<app_id>',
identifier=end_user_id). Запросы под этим юзером помечаются source_type='api',
source_app_id=<app.id>.
"""
from __future__ import annotations

from dataclasses import dataclass

from services import applications, identity
from services.exceptions import InvalidAPIKey


@dataclass(frozen=True)
class AuthorizedAPICall:
    application_id: int
    end_user_internal_id: int


def authorize(api_key: str, end_user_id: str, *, end_user_display_name: str | None = None) -> AuthorizedAPICall:
    """Проверить ключ + (создать/найти) внутреннего юзера для end-user-id."""
    if not api_key or not end_user_id:
        raise InvalidAPIKey("missing api_key or end_user_id")

    app = applications.find_by_api_key(api_key)
    if app is None:
        raise InvalidAPIKey("unknown or revoked api key")

    provider = f"api:{app.id}"
    user_id = identity.find_user_id_by_provider(provider, end_user_id)
    if user_id is None:
        # Создаём внутреннего юзера для этого end-user-id
        new_id = identity._create_user(first_name=end_user_display_name)  # noqa: SLF001
        identity.link_provider(new_id, provider, end_user_id)
        user_id = new_id

    return AuthorizedAPICall(application_id=app.id, end_user_internal_id=user_id)
