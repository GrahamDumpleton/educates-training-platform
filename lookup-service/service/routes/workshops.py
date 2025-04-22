"""REST API handlers for workshop requests."""

import logging
from typing import List

from aiohttp import web

from ..caches.workshopenvironment import WorkshopEnvironment
from .authnz import login_required, roles_accepted

logger = logging.getLogger("educates")


@login_required
@roles_accepted("admin", "tenant")
async def api_get_v1_workshops(request: web.Request) -> web.Response:
    """Returns a list of workshops available."""

    service_state = request.app["service_state"]
    tenant_database = service_state.tenant_database

    # Get the tenant name from the query parameters. This is required when
    # the client role is "tenant".

    tenant_name = request.query.get("tenant")

    client = request["remote_client"]
    client_roles = request["client_roles"]

    if "tenant" in client_roles:
        if not tenant_name:
            logger.warning(
                "Missing tenant name in request from client %r.", client.name
            )

            return web.Response(text="Missing tenant name", status=400)

        client = request["remote_client"]

        if not client.allowed_access_to_tenant(tenant_name):
            return web.Response(text="Client not allowed access to tenant", status=403)

    # Work out the set of portals accessible by the specified tenant.

    if tenant_name:
        tenant = tenant_database.get_tenant(tenant_name)

        if not tenant:
            return web.Response(text="Tenant not available", status=503)

        accessible_portals = tenant.portals_which_are_accessible()

    else:
        # Collect list of portals from all the clusters.

        accessible_portals = []

        cluster_database = service_state.cluster_database

        for cluster in cluster_database.get_clusters():
            accessible_portals.extend(cluster.get_portals())

    # Generate the list of workshops available to the user for this tenant which
    # are in a running state. We need to eliminate any duplicates as a workshop
    # may be available through multiple training portals. We use the title and
    # description from the last found so we expect these to be consistent.

    workshops = {}

    for portal in accessible_portals:
        for environment in portal.get_running_environments():
            workshops[environment.workshop] = {
                "name": environment.workshop,
                "title": environment.title,
                "description": environment.description,
                "labels": environment.labels,
            }

    return web.json_response({"workshops": list(workshops.values())})


@login_required
@roles_accepted("admin", "tenant")
async def api_post_v1_workshops(request: web.Request) -> web.Response:
    """Returns a workshop session for the specified tenant and workshop."""

    data = await request.json()

    service_state = request.app["service_state"]

    decoded_token = request["jwt_token"]
    client = request["remote_client"]

    tenant_name = data.get("tenantName")

    # We will have an "act" field in the decoded token if originally logged in
    # using a voucher token. In this case, we will use the user ID from the
    # token. If there is no "act" field, then we will use the user ID from the
    # client configuration. If there is no user ID in the client configuration,
    # then we will use the user ID from the request data. If there is no user ID
    # in the request data, then we will use an empty string.

    user_id = decoded_token.get("act", {}).get("sub")
    user_id = user_id or client.user
    user_id = user_id or data.get("clientUserId") or ""

    # TODO: Need to see how can use the action ID supplied by the client. At the
    # moment we just log it.

    action_id = data.get("clientActionId") or ""  # pylint: disable=unused-variable

    index_url = data.get("clientIndexUrl") or ""

    user_email = data.get("userEmailAddress") or ""
    user_first_name = data.get("userFirstName") or ""
    user_last_name = data.get("userLastName") or ""

    workshop_name = data.get("workshopName")
    parameters = data.get("workshopParams", [])

    analytics_url = data.get("analyticsWebhookUrl") or ""

    logger.info(
        "Workshop request from client %r for tenant %r, workshop %r, user %r, action %r, analytics %r",
        client.name,
        tenant_name,
        workshop_name,
        user_id,
        action_id,
        analytics_url,
    )

    if not tenant_name:
        logger.warning("Missing tenant name in request from client %r.", client.name)

        return web.Response(text="Missing tenantName", status=400)

    if not workshop_name:
        logger.warning("Missing workshop name in request from client %r.", client.name)

        return web.Response(text="Missing workshopName", status=400)

    # Check that client is allowed access to this tenant.

    if not client.allowed_access_to_tenant(tenant_name):
        logger.warning(
            "Client %r not allowed access to tenant %r", client.name, tenant_name
        )

        return web.Response(text="Client not allowed access to tenant", status=403)

    # If a user ID is supplied, check all of the portals to see if this user
    # already has a workshop session for this workshop. This is done before
    # checking whether a portal is accessible to the tenant so depends on the
    # user ID being unique across all tenants. We do it before checking access
    # to the tenant so that we can return a session if the user already has one
    # even if the tenant no longer has access because of label changes.

    cluster_database = service_state.cluster_database

    if user_id:
        for cluster in cluster_database.get_clusters():
            for portal in cluster.get_portals():
                session = portal.find_existing_workshop_session_for_user(
                    user_id, workshop_name
                )

                if session:
                    data = await session.reacquire_workshop_session(index_url)

                    if data:
                        data["tenantName"] = tenant_name
                        return web.json_response(data)

    # Get the list of portals hosting the workshop and calculate the subset that
    # are accessible to the tenant.

    tenant_database = service_state.tenant_database

    tenant = tenant_database.get_tenant(tenant_name)

    if not tenant:
        logger.error("Configuration for tenant %r could not be found", tenant_name)

        return web.Response(text="Tenant not available", status=503)

    accessible_portals = tenant.portals_which_are_accessible()

    selected_portals = []

    for portal in accessible_portals:
        if portal.hosts_workshop(workshop_name):
            selected_portals.append(portal)

    # If there are no resulting portals, then the workshop is not available to
    # the tenant.

    if not selected_portals:
        logger.warning(
            "Workshop %s requested by client %r not available to tenant %r",
            workshop_name,
            client.name,
            tenant_name,
        )

        return web.Response(text="Workshop not available", status=503)

    # Find the set of workshop environments for the specified workshop that are
    # in a running state. If there are no such environments, then the workshop
    # is not available.

    environments = []

    for portal in selected_portals:
        for environment in portal.get_running_environments():
            if environment.workshop == workshop_name:
                environments.append(environment)

    if not environments:
        logger.warning(
            "Workshop %r requested by client %r not available",
            workshop_name,
            client.name,
        )

        return web.Response(text="Workshop not available", status=503)

    # Sort the workshop environments so that those deemed to be the best
    # candidates for running a workshop session are at the front of the list.

    environments = sort_workshop_environments(environments)

    # Loop over the workshop environments and try to allocate a session.

    for environment in environments:
        data = await environment.request_workshop_session(
            user_id,
            user_email,
            user_first_name,
            user_last_name,
            parameters,
            index_url,
            analytics_url,
        )

        if data:
            data["tenantName"] = tenant_name
            return web.json_response(data)

    # If we get here, then we don't believe there is any available capacity for
    # creating a workshop session.

    logger.warning(
        "Workshop %r requested by client %r not available", workshop_name, client.name
    )

    return web.Response(text="Workshop not available", status=503)


def sort_workshop_environments(
    environments: List[WorkshopEnvironment],
) -> List[WorkshopEnvironment]:
    """Sort the list of workshop environments such that those deemed to be the
    best candidates for running a workshop session are at the front of the
    list."""

    def score_based_on_portal_availability(environment: WorkshopEnvironment) -> int:
        """Return a score based on the remaining capacity of the portal hosting
        the workshop environment. Note that at this point we only return 0 or 1
        indicating whether there is any capacity left or not and not how much
        capacity."""

        # If the portal doesn't have a maximum capacity specified and as such
        # there is no limit to the number of workshop sessions return 1.

        if not environment.portal.capacity:
            return 1

        # If the portal has a maximum capacity specified and there is no more
        # capacity left, return 0.

        if environment.portal.capacity - environment.portal.allocated <= 0:
            return 0

        # Otherwise return 1 indicating there is capacity.

        return 1

    def score_based_on_environment_availability(
        environment: WorkshopEnvironment,
    ) -> int:
        """Return a score based on the remaining capacity of the workshop
        environment. Note that at this point we only return 0 or 1 indicating
        whether there is any capacity left or not and not how much capacity."""

        # If the environment doesn't have a maximum capacity specified and as
        # such there is no limit to the number of workshop sessions return 1.

        if not environment.capacity:
            return 1

        # If the environment has a maximum capacity specified and there is no
        # more capacity left, return 0.

        if environment.capacity - environment.allocated <= 0:
            return 0

        # Otherwise return 1 indicating there is capacity.

        return 1

    def score_based_on_reserved_sessions(environment: WorkshopEnvironment) -> int:
        """Return a score based on the number of reserved sessions currently
        available for the workshop environment. Where as we didn't before, we
        also take into account the actual available capacity of the portal
        hosting the workshop environment."""

        # If the portal doesn't have a maximum capacity specified we treat it
        # as if there is only 1 spot left so that we give priority to portals
        # that do specify an actual capacity.

        capacity = 1

        if environment.portal.capacity:
            capacity = environment.portal.capacity - environment.portal.allocated

        # Return the capacity of the portal in conjunction with the number of
        # reserved sessions which are currently available.

        return (capacity, environment.available)

    def score_based_on_available_capacity(environment: WorkshopEnvironment) -> int:
        """Return a score based on the available capacity of the workshop
        environment. Where as we didn't before, we also take into account the
        actual available capacity of the portal hosting the workshop
        environment."""

        # If the portal doesn't have a maximum capacity specified we treat it
        # as if there is only 1 spot left so that we give priority to portals
        # that do specify an actual capacity.

        capacity = 1

        if environment.portal.capacity:
            capacity = environment.portal.capacity - environment.portal.allocated

        # If the environment doesn't have a maximum capacity specified we treat
        # it as if there is only 1 spot left so that we give priority to
        # environments that do specify an actual capacity.

        if not environment.capacity:
            return (capacity, 1)

        # Return the capacity of the portal in conjunction with the available
        # capacity of the workshop environment.

        return (capacity, environment.capacity - environment.allocated)

    return sorted(
        environments,
        key=lambda environment: (
            score_based_on_portal_availability(environment),
            score_based_on_environment_availability(environment),
            score_based_on_reserved_sessions(environment),
            score_based_on_available_capacity(environment),
        ),
        reverse=True,
    )


# Set up the routes for the workshop management API.

routes = [
    web.get("/api/v1/workshops", api_get_v1_workshops),
    web.post("/api/v1/workshops", api_post_v1_workshops),
]
