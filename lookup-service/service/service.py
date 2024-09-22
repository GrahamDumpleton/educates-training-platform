"""Custom operator context object for the service."""

from dataclasses import dataclass

from .caches.databases import (
    AccessDatabase,
    ClientDatabase,
    TenantDatabase,
    ClusterDatabase,
)


@dataclass
class ServiceState:
    """Custom operator context object for the service."""

    access_database: AccessDatabase
    client_database: ClientDatabase
    tenant_database: TenantDatabase
    cluster_database: ClusterDatabase

    def __copy__(self) -> "ServiceState":
        return self
