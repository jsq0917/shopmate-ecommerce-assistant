"""Authentication endpoints: captcha, register, login, refresh, logout, me.

Refresh tokens are opaque, stored only as SHA-256 digests, rotated on use and revoked on
logout. The access token is a short-lived JWT carrying identity, tenant and role. Identity
always comes from the token or the cookie, never from a request body.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shopmate_ecommerce_assistant.api.deps import (
    client_ip,
    get_access_context,
    get_rate_limiter,
    get_request_ids,
    get_session,
    get_settings_dep,
)
from shopmate_ecommerce_assistant.api.envelope import Envelope
from shopmate_ecommerce_assistant.api.schemas import (
    CaptchaData,
    LoginRequest,
    LogoutData,
    MeData,
    RegisterRequest,
    TokenData,
    UserSummary,
)
from shopmate_ecommerce_assistant.core.config import Settings
from shopmate_ecommerce_assistant.core.errors import ErrorCode, ToolError
from shopmate_ecommerce_assistant.core.rate_limit import RateLimiter
from shopmate_ecommerce_assistant.core.security import (
    AccessContext,
    AuthError,
    hash_password,
    issue_access_token,
    issue_captcha,
    new_csrf_token,
    new_refresh_token,
    permissions_for,
    sha256_digest,
    verify_captcha,
    verify_password,
)
from shopmate_ecommerce_assistant.db.models.enums import UserRole
from shopmate_ecommerce_assistant.db.repositories.auth import (
    RefreshSessionRepository,
    UserRepository,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REGISTER_DUPLICATE = "该邮箱已注册，请直接登录。"


async def _throttle(request: Request, limiter: RateLimiter, *, key: str, limit: int) -> None:
    allowed, retry_after = await limiter.check(key, limit=limit, window_seconds=60)
    if not allowed:
        raise ToolError(
            ErrorCode.RATE_LIMITED,
            "请求过于频繁，请稍后重试。",
            retryable=True,
            retry_after_ms=int(retry_after * 1000),
        )


def _set_auth_cookies(
    response: Response, settings: Settings, *, refresh_token: str, csrf_token: str
) -> None:
    secure = settings.app_env == "production"
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def _user_summary(user) -> UserSummary:
    return UserSummary(
        user_id=user.id,
        email=user.email_ci,
        display_name_masked=user.display_name_masked,
        role=user.role.value,
        shop_id=user.shop_id,
        is_synthetic=bool(user.is_synthetic),
    )


@router.get("/captcha", response_model=Envelope[CaptchaData])
async def captcha(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Envelope[CaptchaData]:
    challenge = issue_captcha(settings)
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=CaptchaData(
            captcha_token=challenge.token,
            question=challenge.question,
            expires_in_seconds=settings.captcha_ttl_seconds,
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("/register", response_model=Envelope[UserSummary], status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Envelope[UserSummary]:
    await _throttle(
        request,
        limiter,
        key=f"auth:register:{client_ip(request)}",
        limit=settings.rate_limit_auth_per_minute,
    )
    if not verify_captcha(settings, body.captcha_token, body.captcha_answer):
        raise ToolError(ErrorCode.VALIDATION_ERROR, "验证码错误或已过期，请重新获取。")

    users = UserRepository(session)
    shop_id = await users.get_default_shop_id()
    existing = await users.get_by_email(shop_id=shop_id, email=body.email)
    if existing is not None:
        raise ToolError(ErrorCode.VALIDATION_ERROR, REGISTER_DUPLICATE)

    try:
        user = await users.create(
            shop_id=shop_id,
            email=body.email,
            password_hash=hash_password(body.password),
            role=UserRole.SHOPPER,
            display_name_masked=_mask_email(body.email),
        )
    except IntegrityError:
        raise ToolError(ErrorCode.VALIDATION_ERROR, REGISTER_DUPLICATE) from None

    request_id, trace_id = get_request_ids(request)
    return Envelope(data=_user_summary(user), request_id=request_id, trace_id=trace_id)


@router.post("/login", response_model=Envelope[TokenData])
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Envelope[TokenData]:
    await _throttle(
        request,
        limiter,
        key=f"auth:login:{client_ip(request)}",
        limit=settings.rate_limit_auth_per_minute,
    )
    if not verify_captcha(settings, body.captcha_token, body.captcha_answer):
        raise ToolError(ErrorCode.VALIDATION_ERROR, "验证码错误或已过期，请重新获取。")

    users = UserRepository(session)
    shop_id = await users.get_default_shop_id()
    user = await users.get_by_email(shop_id=shop_id, email=body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise AuthError("UNAUTHENTICATED", "邮箱或密码不正确。")
    if not user.is_active:
        raise AuthError("UNAUTHENTICATED", "该账号已停用。")

    await users.touch_last_login(shop_id=shop_id, user_id=user.id)

    context = AccessContext(
        shop_id=shop_id, user_id=user.id, role=user.role, permissions=permissions_for(user.role)
    )
    access_token = issue_access_token(settings, context)
    refresh_token = new_refresh_token()
    csrf_token = new_csrf_token()

    refresh_repo = RefreshSessionRepository(session)
    await refresh_repo.create(
        shop_id=shop_id,
        user_id=user.id,
        token_hash=sha256_digest(refresh_token),
        csrf_token_hash=sha256_digest(csrf_token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    _set_auth_cookies(response, settings, refresh_token=refresh_token, csrf_token=csrf_token)

    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=TokenData(
            access_token=access_token,
            expires_in_seconds=settings.access_token_ttl_seconds,
            user=_user_summary(user),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("/refresh", response_model=Envelope[TokenData])
async def refresh(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> Envelope[TokenData]:
    await _throttle(
        request,
        limiter,
        key=f"auth:refresh:{client_ip(request)}",
        limit=settings.rate_limit_auth_per_minute,
    )
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    csrf_header = request.headers.get("x-csrf-token")
    if not refresh_token or not csrf_cookie or csrf_header != csrf_cookie:
        raise AuthError("CSRF_INVALID", "会话校验失败，请重新登录。")

    refresh_repo = RefreshSessionRepository(session)
    token_hash = sha256_digest(refresh_token)
    session_row = await refresh_repo.get_active(token_hash=token_hash)
    if session_row is None:
        raise AuthError("UNAUTHENTICATED", "登录状态已失效，请重新登录。")

    users = UserRepository(session)
    user = await users.get(shop_id=session_row.shop_id, user_id=session_row.user_id)
    if user is None or not user.is_active:
        raise AuthError("UNAUTHENTICATED", "该账号已停用。")

    context = AccessContext(
        shop_id=session_row.shop_id,
        user_id=session_row.user_id,
        role=user.role,
        permissions=permissions_for(user.role),
    )
    access_token = issue_access_token(settings, context)
    new_refresh = new_refresh_token()
    new_csrf = new_csrf_token()

    new_row = await refresh_repo.create(
        shop_id=session_row.shop_id,
        user_id=session_row.user_id,
        token_hash=sha256_digest(new_refresh),
        csrf_token_hash=sha256_digest(new_csrf),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.refresh_token_ttl_seconds),
    )
    await refresh_repo.rotate(session_id=session_row.id, replaced_by_id=new_row.id)
    _set_auth_cookies(response, settings, refresh_token=new_refresh, csrf_token=new_csrf)

    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=TokenData(
            access_token=access_token,
            expires_in_seconds=settings.access_token_ttl_seconds,
            user=_user_summary(user),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


@router.post("/logout", response_model=Envelope[LogoutData])
async def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[LogoutData]:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if refresh_token:
        refresh_repo = RefreshSessionRepository(session)
        row = await refresh_repo.get_active(token_hash=sha256_digest(refresh_token))
        if row is not None:
            await refresh_repo.revoke(session_id=row.id)
    response.delete_cookie(settings.refresh_cookie_name, path="/api/v1/auth")
    response.delete_cookie(settings.csrf_cookie_name, path="/api/v1/auth")
    request_id, trace_id = get_request_ids(request)
    return Envelope(data=LogoutData(), request_id=request_id, trace_id=trace_id)


@router.get("/me", response_model=Envelope[MeData])
async def me(
    request: Request,
    context: Annotated[AccessContext, Depends(get_access_context)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Envelope[MeData]:
    users = UserRepository(session)
    user = await users.get(shop_id=context.shop_id, user_id=context.user_id)
    if user is None:
        raise AuthError("UNAUTHENTICATED", "登录状态已失效，请重新登录。")
    request_id, trace_id = get_request_ids(request)
    return Envelope(
        data=MeData(
            user_id=user.id,
            display_name_masked=user.display_name_masked,
            email=user.email_ci,
            role=user.role.value,
            shop_id=user.shop_id,
            permissions=sorted(context.permissions),
        ),
        request_id=request_id,
        trace_id=trace_id,
    )


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


__all__ = ["router"]
