"""Handles the workshop allocation custom resource."""

import logging
import base64

import kopf
import pykube

from .objects import create_from_dict
from .helpers import xget, substitute_variables
from .analytics import report_analytics_event


from .operator_config import (
    OPERATOR_API_GROUP,
    OPERATOR_STATUS_KEY,
)

api = pykube.HTTPClient(pykube.KubeConfig.from_env())

logger = logging.getLogger("educates")


@kopf.index(
    "",
    "v1",
    "secrets",
    labels={
        f"training.{OPERATOR_API_GROUP}/component": "session",
        f"training.{OPERATOR_API_GROUP}/component.group": "variables",
    },
)
def session_variables_secret_index(
    namespace,
    name,
    body,
    **_,
):
    """Keeps an index of the session variables secrets for a workshop sessions.
    This is used to look up the session variables for a given session so that
    variables can be used in expanding the request objects."""

    logger.info("Adding session variables secret %s to cache.", name)

    return {(namespace, name): body.get("data", {})}


@kopf.index(
    "",
    "v1",
    "secrets",
    labels={
        f"training.{OPERATOR_API_GROUP}/component": "request",
        f"training.{OPERATOR_API_GROUP}/component.group": "variables",
    },
)
def request_variables_secret_index(
    namespace,
    name,
    body,
    **_,
):
    """Keeps an index of the request variables secrets for a workshop session.
    This is used to look up the request variables for a given session so that
    variables can be used in expanding the request objects. Note that the
    request variables secret would only be created at the time of requesting a
    workshop session, which may be sometime after when the workshop session
    was actually created."""

    logger.info("Adding request variables secret %s to cache.", name)

    return {(namespace, name): body.get("data", {})}


@kopf.on.resume(
    f"training.{OPERATOR_API_GROUP}",
    "v1beta1",
    "workshopallocations",
    id=OPERATOR_STATUS_KEY,
)
def workshop_allocation_resume(name, **_):
    """Used to acknowledge that an existing workshop allocation request has been
    processed. This is because when the operator is restarted, the workshop
    allocation request for an active workshop session will still exist in the
    cluster."""

    logger.info(
        "Workshop allocation request %s has been found but was previously processed.",
        name,
    )


@kopf.on.create(
    f"training.{OPERATOR_API_GROUP}",
    "v1beta1",
    "workshopallocations",
    id=OPERATOR_STATUS_KEY,
)
def workshop_allocation_create(
    name,
    uid,
    meta,
    spec,
    patch,
    runtime,
    retry,
    workshop_environment_index,
    workshop_session_index,
    session_variables_secret_index,
    request_variables_secret_index,
    **_,
):  # pylint: disable=redefined-outer-name
    """Process a workshop allocation request, creating the request objects
    for the workshop session. Will also set the status of the workshop
    allocation request to "Allocated" to indicate that the request has been
    processed."""

    portal_name = meta.get("labels", {}).get(
        f"training.{OPERATOR_API_GROUP}/portal.name", ""
    )

    environment_name = spec["environment"]["name"]
    workshop_namespace = environment_name

    session_name = spec["session"]["name"]
    session_namespace = session_name

    session_variables_secret_name = f"{session_name}-session"
    request_variables_secret_name = f"{session_name}-request"

    logger.info(
        "Processing workshop allocation request %s against workshop session %s of workshop environment %s, retries %d.",
        name,
        session_name,
        environment_name,
        retry,
    )

    # Check if the workshop environment and workshop session related to this
    # workshop allocation request exist in the cache. This is to avoid possible
    # race condition when process is starting up or there is a back log of
    # resource events for the operator to handle. We backup and retry if the
    # resources are not found in the cache but give up eventually. If for some
    # reason don't exist in the cache by the time we give up, we will fail the
    # request.

    if not (None, environment_name) in workshop_environment_index:
        if runtime.total_seconds() >= 45:
            # If the workshop environment is not found in the cache after 45
            # seconds, we will fail the request. This is to avoid waiting
            # indefinitely for the workshop environment to be registered. Make
            # sure to set the status to "Failed" to indicate that the request
            # has failed. Do note however that the actual workshop session will
            # still be usable except that any request objects will not have been
            # created. The only indication that the request has failed is the
            # status of the workshop allocation request.

            patch["status"] = {
                OPERATOR_STATUS_KEY: {
                    "phase": "Failed",
                    "message": f"Workshop environment {environment_name} is not available.",
                }
            }

            report_analytics_event(
                "Resource/PermanentError",
                {
                    "kind": "WorkshopAllocation",
                    "name": name,
                    "uid": uid,
                    "retry": retry,
                    "message": f"Workshop environment {environment_name} is not available.",
                },
            )

            raise kopf.PermanentError(
                f"In processing workshop allocation request {name}, the workshop environment {environment_name} is not available."
            )

        # If the workshop environment is not found in the cache, we will retry
        # the request after a short delay. Make sure to set the status to
        # "Pending" to indicate that the request is still being processed.

        patch["status"] = {OPERATOR_STATUS_KEY: {"phase": "Pending"}}

        raise kopf.TemporaryError(
            f"In processing workshop allocation request {name}, no record of workshop environment {environment_name} currently exists.",
            delay=5,
        )

    environment_instance, *_ = workshop_environment_index[(None, environment_name)]

    if not (None, session_name) in workshop_session_index:
        if runtime.total_seconds() >= 45:
            # If the workshop session is not found in the cache after 45
            # seconds, we will fail the request. This is to avoid waiting
            # indefinitely for the workshop session to be registered. Make sure
            # to set the status to "Failed" to indicate that the request has
            # failed. Do note however that the actual workshop session will
            # still be usable except that any request objects will not have been
            # created. The only indication that the request has failed is the
            # status of the workshop allocation request.

            patch["status"] = {
                OPERATOR_STATUS_KEY: {
                    "phase": "Failed",
                    "message": f"Workshop session {session_name} is not available.",
                }
            }

            report_analytics_event(
                "Resource/PermanentError",
                {
                    "kind": "WorkshopAllocation",
                    "name": name,
                    "uid": uid,
                    "retry": retry,
                    "message": f"Workshop session {session_name} is not available.",
                },
            )

            raise kopf.PermanentError(
                f"In processing workshop allocation request {name}, the workshop session {session_name} is not available."
            )

        # If the workshop session is not found in the cache, we will retry the
        # request after a short delay. Make sure to set the status to "Pending"
        # to indicate that the request is still being processed.

        patch["status"] = {OPERATOR_STATUS_KEY: {"phase": "Pending"}}

        raise kopf.TemporaryError(
            f"In processing workshop allocation request {name}, no record of workshop session {session_name} currently exists.",
            delay=5,
        )

    # Note that we are not using the workshop session instance here. We are
    # only checking if the workshop session exists in the cache as a sanity
    # check. The information we need about request objects is actually in the
    # status of the workshop environment instance.

    # session_instance, *_ = workshop_session_index[(None, session_name)]

    # Check if the session variables and request variables secrets exist in the
    # cache. If they do not exist, we will retry the request after a short
    # delay. If they do not exist after a certain period of time, we will fail
    # the request. This is to avoid waiting indefinitely for the secrets to be
    # created.

    if (
        not (workshop_namespace, session_variables_secret_name)
        in session_variables_secret_index
    ):
        if runtime.total_seconds() >= 45:
            # If the session variables secret is not found in the cache after 45
            # seconds, we will fail the request. This is to avoid waiting
            # indefinitely for the session variables secret to be created. Make
            # sure to set the status to "Failed" to indicate that the request has
            # failed. Do note however that the actual workshop session will still
            # be usable except that any request objects will not have been
            # created. The only indication that the request has failed is the
            # status of the workshop allocation request.

            patch["status"] = {
                OPERATOR_STATUS_KEY: {
                    "phase": "Failed",
                    "message": f"Session variables secret {session_variables_secret_name} is not available.",
                }
            }

            report_analytics_event(
                "Resource/PermanentError",
                {
                    "kind": "WorkshopAllocation",
                    "name": name,
                    "uid": uid,
                    "retry": retry,
                    "message": f"Session variables secret {session_variables_secret_name} is not available.",
                },
            )

            raise kopf.PermanentError(
                f"Session variables secret {session_variables_secret_name} is not available."
            )

        # If the session variables secret is not found in the cache, we will
        # retry the request after a short delay. Make sure to set the status to
        # "Pending" to indicate that the request is still being processed.

        patch["status"] = {OPERATOR_STATUS_KEY: {"phase": "Pending"}}

        raise kopf.TemporaryError(
            f"No record of variables secret {session_variables_secret_name}.", delay=5
        )

    if (
        not (workshop_namespace, request_variables_secret_name)
        in request_variables_secret_index
    ):
        if runtime.total_seconds() >= 45:
            # If the parameters secret is not found in the cache after 45
            # seconds, we will fail the request. This is to avoid waiting
            # indefinitely for the parameters secret to be created. Make sure to
            # set the status to "Failed" to indicate that the request has failed.
            # Do note however that the actual workshop session will still be
            # usable except that any request objects will not have been created.
            # The only indication that the request has failed is the status of
            # the workshop allocation request.

            patch["status"] = {
                OPERATOR_STATUS_KEY: {
                    "phase": "Failed",
                    "message": f"Request variables secret {request_variables_secret_name} is not available.",
                }
            }

            report_analytics_event(
                "Resource/PermanentError",
                {
                    "kind": "WorkshopAllocation",
                    "name": name,
                    "uid": uid,
                    "retry": retry,
                    "message": f"Request variables secret {request_variables_secret_name} is not available.",
                },
            )

            raise kopf.PermanentError(
                f"Request variables secret {request_variables_secret_name} is not available."
            )

        # If the request variables secret is not found in the cache, we will
        # retry the request after a short delay. Make sure to set the status to
        # "Pending" to indicate that the request is still being processed.

        patch["status"] = {OPERATOR_STATUS_KEY: {"phase": "Pending"}}

        raise kopf.TemporaryError(
            f"No record of parameters secret {request_variables_secret_name}.", delay=5
        )

    # Get the session variables and request variables from the cache.

    cached_session_variables, *_ = session_variables_secret_index[
        (workshop_namespace, session_variables_secret_name)
    ]

    cached_request_variables, *_ = request_variables_secret_index[
        (workshop_namespace, request_variables_secret_name)
    ]

    # Combine the session variables and request variables into a single
    # dictionary. Since the session variables and request variables are stored
    # in the secrets as base64 encoded strings, we need to decode them before
    # using them.

    all_data_variables = {}

    for key, value in cached_request_variables.items():
        all_data_variables[key] = base64.b64decode(value.encode("UTF-8")).decode(
            "UTF-8"
        )

    for key, value in cached_session_variables.items():
        all_data_variables[key] = base64.b64decode(value.encode("UTF-8")).decode(
            "UTF-8"
        )

    # Get the workshop name and the request objects from the status of the
    # workshop environment instance.

    workshop_name = xget(
        environment_instance, f"status.{OPERATOR_STATUS_KEY}.workshop.name"
    )

    workshop_spec = xget(
        environment_instance, f"status.{OPERATOR_STATUS_KEY}.workshop.spec"
    )

    objects = []

    if workshop_spec.get("request"):
        objects.extend(workshop_spec["request"].get("objects", []))

    # Create the request objects for the workshop session.

    for object_body in objects:
        # Substitute any data variables in the request objects.

        object_body = substitute_variables(object_body, all_data_variables)

        # Set the namespace on the request object to the session namespace if it
        # is not already set.

        if not object_body["metadata"].get("namespace"):
            object_body["metadata"]["namespace"] = session_namespace

        # Set the labels on the request object to indicate that it was created
        # for this specific workshop session.

        object_body["metadata"].setdefault("labels", {}).update(
            {
                f"training.{OPERATOR_API_GROUP}/component": "request",
                f"training.{OPERATOR_API_GROUP}/component.group": "objects",
                f"training.{OPERATOR_API_GROUP}/workshop.name": workshop_name,
                f"training.{OPERATOR_API_GROUP}/portal.name": portal_name,
                f"training.{OPERATOR_API_GROUP}/environment.name": environment_name,
                f"training.{OPERATOR_API_GROUP}/session.name": session_name,
                f"training.{OPERATOR_API_GROUP}/session.objects": "true",
            }
        )

        # Adopt the request objects so that they are owned by the workshop
        # allocation custom resource. This way they will be deleted
        # automatically when the workshop allocation custom resource is deleted.

        kopf.adopt(object_body)

        try:
            object_name = object_body["metadata"]["name"]
            object_namespace = object_body["metadata"]["namespace"]
            object_type = object_body["kind"]

            logger.debug(
                "Creating workshop request object %s of type %s in namespace %s for session %s.",
                object_name,
                object_type,
                object_namespace,
                session_name,
            )

            create_from_dict(object_body)

        except Exception as exc:
            logger.exception(
                "Unable to create workshop request objects for session, failed on creating workshop request object %s of type %s in namespace %s for session %s.",
                object_name,
                object_type,
                object_namespace,
                session_name,
            )

            patch["status"] = {
                OPERATOR_STATUS_KEY: {
                    "phase": "Failed",
                    "message": f"Unable to create workshop request objects for session, failed on creating workshop request object {object_name} of type {object_type} in namespace {object_namespace} for session {session_name}.",
                }
            }

            raise kopf.PermanentError(
                f"Unable to create workshop request objects for session, failed on creating workshop request object {object_name} of type {object_type} in namespace {object_namespace} for session {session_name}."
            ) from exc

    # Set the status of the workshop allocation request to "Allocated" to
    # indicate that the request has been processed.

    return {
        "phase": "Allocated",
        "message": None,
    }


@kopf.on.delete(
    f"training.{OPERATOR_API_GROUP}", "v1beta1", "workshopallocations", optional=True
)
def workshop_allocation_delete(name, **_):
    """Nothing to do here at this point because the owner references will
    ensure that everything is cleaned up appropriately."""

    # NOTE: This doesn't actually get called because we as we marked it as
    # optional to avoid a finalizer being added to the custom resource, so we
    # use separate generic event handler below to log when the workshop
    # allocation request is deleted.


@kopf.on.event(f"training.{OPERATOR_API_GROUP}", "v1beta1", "workshopallocations")
def workshop_allocation_event(type, event, **_): #pylint: disable=redefined-builtin
    """Log when a workshop allocation request is deleted."""

    if type == "DELETED":
        logger.info("Workshop allocation request %s deleted.", event["object"]["metadata"]["name"])
