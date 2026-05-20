"""ORM models. Importing this package registers all models on `Base.metadata`."""

from app.db.models.accounting import AccountingRecord
from app.db.models.admin import AuditLog, LocalAdmin, WebSession
from app.db.models.domain import Authorization, Device, DeviceGroup, PrivilegeProfile
from app.db.models.identity import ADGroup, User, UserADGroup
from app.db.models.system import SystemSecret, SystemSetting

__all__ = [
    "ADGroup",
    "AccountingRecord",
    "AuditLog",
    "Authorization",
    "Device",
    "DeviceGroup",
    "LocalAdmin",
    "PrivilegeProfile",
    "SystemSecret",
    "SystemSetting",
    "User",
    "UserADGroup",
    "WebSession",
]
