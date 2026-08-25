import hmac
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    actor: str


async def get_tenant_context(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> TenantContext:
    if settings.auth_enabled:
        supplied = x_api_key or ""
        expected = settings.app_api_key or ""
        if not hmac.compare_digest(supplied, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-API-Key",
            )
    tenant_id = (x_tenant_id or settings.default_tenant_id).strip()
    if not tenant_id or len(tenant_id) > 80:
        raise HTTPException(status_code=400, detail="Invalid X-Tenant-ID")
    return TenantContext(tenant_id=tenant_id, actor="CEO")
