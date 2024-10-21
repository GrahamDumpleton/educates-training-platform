"""Operator handlers for client configuration resources."""

import datetime
import logging
from typing import Any, Dict

import kopf

from ..caches.clientconfig import ClientConfig
from ..helpers.objects import xgetattr
from ..service import ServiceState

logger = logging.getLogger("educates")


@kopf.on.resume("clientconfigs.lookup.educates.dev")
@kopf.on.create("clientconfigs.lookup.educates.dev")
@kopf.on.update("clientconfigs.lookup.educates.dev")
def clientconfigs_update(
    name: str, meta: kopf.Meta, spec: kopf.Spec, memo: ServiceState, reason: str, **_
) -> Dict[str, Any]:
    """Add the client configuration to the client database."""

    generation = meta["generation"]

    client_name = name

    client_uid = xgetattr(meta, "uid")

    client_password = xgetattr(spec, "client.password")

    client_user = xgetattr(spec, "client.user")

    # The "user" field was deprecated in favor of "client.user". Accept the
    # "user" field if "client.user" is not provided for backwards compatibility.

    if not client_user:
        client_user = xgetattr(spec, "user")

    client_issuer = xgetattr(spec, "client.proxy.issuer")
    client_proxy = xgetattr(spec, "client.proxy.secret", "")

    client_tenants = xgetattr(spec, "tenants", [])

    client_roles = xgetattr(spec, "roles", [])

    logger.info(
        "%s client configuration %r with generation %s.",
        (reason == "update") and "Update" or "Register",
        name,
        generation,
    )

    client_database = memo.client_database

    time_now = datetime.datetime.now(datetime.timezone.utc)

    client_database.update_client(
        ClientConfig(
            name=client_name,
            uid=client_uid,
            start=int(time_now.timestamp()),
            password=client_password,
            user=client_user,
            issuer=client_issuer,
            proxy=client_proxy,
            tenants=client_tenants,
            roles=client_roles,
        )
    )

    return {}


@kopf.on.delete("clientconfigs.lookup.educates.dev")
def clientconfigs_delete(name: str, meta: kopf.Meta, memo: ServiceState, **_) -> None:
    """Remove the client configuration from the client database."""

    generation = meta["generation"]

    client_database = memo.client_database

    client_name = name

    logger.info(
        "Discard client configuration %r with generation %s.", client_name, generation
    )

    client_database.remove_client(client_name)
