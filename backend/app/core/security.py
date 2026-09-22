"""密码哈希与 JWT 签发/校验。

- 密码用 bcrypt 库直接调用（决策 D5），不引入 passlib。
- JWT 用 PyJWT（决策 D6）。payload 里带 `tv`(token_version)，
  用户改密/被强制下线时递增该值，从而让已签发的 token 立即失效（F6.4）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, timedelta

import bcrypt
import jwt

from app.core.clock import utcnow
from app.core.config import settings
from app.core.constants import TokenType
from app.core.errors import UnauthorizedError

#: bcrypt 的硬性输入上限（字节，不是字符）。超长输入在 4.x 会直接抛 ValueError，
#: 这里显式截断以避免登录变成 500；schema 层另有 max_length 保证用户不会静默丢字符。
BCRYPT_MAX_BYTES = 72


def _to_bytes(plain: str) -> bytes:
    return plain.encode("utf-8")[:BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("ascii"))
    except (ValueError, TypeError):
        # 库里存了非法 hash（历史脏数据）时按验证失败处理，不要 500
        return False


@dataclass(frozen=True, slots=True)
class TokenPayload:
    user_id: int
    token_version: int
    expires_at: int


def create_token(
    *,
    user_id: int,
    token_version: int,
    token_type: TokenType,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    """返回 (token, 过期的 unix 秒)。"""
    if expires_minutes is None:
        expires_minutes = (
            settings.access_token_expire_minutes
            if token_type is TokenType.ACCESS
            else settings.refresh_token_expire_minutes
        )
    now = utcnow()
    expires = now + timedelta(minutes=expires_minutes)
    payload = {
        "sub": str(user_id),
        "tv": token_version,
        "type": str(token_type),
        "iat": now,
        "exp": expires,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    expires_at = int(expires.replace(tzinfo=UTC).timestamp())
    return token, expires_at


def decode_token(token: str, *, expected_type: TokenType) -> TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("登录已过期，请重新登录", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("登录凭证无效", code="TOKEN_INVALID") from exc

    if payload.get("type") != str(expected_type):
        raise UnauthorizedError("登录凭证类型不匹配", code="TOKEN_TYPE_MISMATCH")

    try:
        user_id = int(payload["sub"])
        token_version = int(payload.get("tv", 0))
        expires_at = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UnauthorizedError("登录凭证无效", code="TOKEN_INVALID") from exc

    return TokenPayload(user_id=user_id, token_version=token_version, expires_at=expires_at)
