"""ORM models. Importing this package registers all models on `Base.metadata`."""

from app.db.models.domain import Authorization, Device, DeviceGroup, PrivilegeProfile
from app.db.models.identity import ADGroup, User, UserADGroup
from app.db.models.system import SystemSecret, SystemSetting

__all__ = [
    "ADGroup",
    "Authorization",
    "Device",
    "DeviceGroup",
    "PrivilegeProfile",
    "SystemSecret",
    "SystemSetting",
    "User",
    "UserADGroup",
]
