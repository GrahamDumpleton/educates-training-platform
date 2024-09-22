"""Operator handlers for client configuration resources."""

import logging
from typing import Any, Dict

import kopf

from ..caches.access import AccessConfig
from ..helpers.objects import xgetattr
from ..service import ServiceState

logger = logging.getLogger("educates")


@kopf.on.resume("accessconfigs.lookup.educates.dev")
@kopf.on.create("accessconfigs.lookup.educates.dev")
@kopf.on.update("accessconfigs.lookup.educates.dev")
def accessconfigs_update(
    name: str, meta: kopf.Meta, spec: kopf.Spec, memo: ServiceState, reason: str, **_
) -> Dict[str, Any]:
    """Add the access configuration to the client database."""

    generation = meta["generation"]

    config_name = name
    allowed_origins = xgetattr(spec, "allowedOrigins", [])

    logger.info(
        "%s access configuration %r with generation %s.",
        (reason == "update") and "Update" or "Register",
        name,
        generation,
    )

    access_database = memo.access_database

    access_database.update_config(
        AccessConfig(
            name=config_name,
            allowed_origins=allowed_origins,
        )
    )

    return {}


@kopf.on.delete("accessconfigs.lookup.educates.dev")
def accessconfigs_delete(name: str, meta: kopf.Meta, memo: ServiceState, **_) -> None:
    """Remove the access configuration from the client database."""

    generation = meta["generation"]

    access_database = memo.access_database

    config_name = name

    logger.info(
        "Discard client configuration %r with generation %s.", config_name, generation
    )

    access_database.remove_client(config_name)
