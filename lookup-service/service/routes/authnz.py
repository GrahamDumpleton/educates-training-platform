"""HTTP API handlers and decorators for controlling access to the REST API.
This includes the middleware for handling CORS headers and the middleware for
handling JWT tokens for authentication and authorization.
"""

import datetime
import fnmatch
import logging
from typing import List, Callable

import jwt
from aiohttp import web

from ..config import jwt_token_secret
from ..caches.clientconfig import ClientConfig

TOKEN_EXPIRATION = 72  # Expiration in hours.

logger = logging.getLogger("educates")


def origin_is_allowed(request_origin, allowed_origins):
    """We need to check whether the request origin matches any of the allowed
    origins. This must be an exact match, or a wildcard match."""

    for allowed_origin in allowed_origins:
        if fnmatch.fnmatch(request_origin, allowed_origin):
            return True

    return False


@web.middleware
async def cors_allow_origin(
    request: web.Request, handler: Callable[..., web.Response]
) -> web.Response:
    """Middleware to add the CORS header to the response."""

    # We need to check to see if any of the access configs have specified a
    # list of allowed origins. If they have, we need to check the origin of the
    # request and only allow it if it is in the list of allowed origins.

    service_state = request.app["service_state"]
    cors_database = service_state.cors_database

    allowed_origins = []

    for browser_config in cors_database.get_configs():
        allowed_origins.extend(browser_config.allowed_origins)

    request_origin = request.headers.get("Origin") or ""

    access_permitted = origin_is_allowed(request_origin, allowed_origins)

    if request.method == "OPTIONS":
        response = web.Response(status=204)

        if allowed_origins and access_permitted:
            response.headers["Access-Control-Allow-Origin"] = request_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type"
            )

        return response

    response = await handler(request)

    if allowed_origins and access_permitted:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"

    return response


def generate_login_response(
    request: web.Request, client: ClientConfig, expires_at: int = None, user: str = None
) -> dict:
    """Generate a JWT token for the client. The token will be set to expire and
    will need to be renewed. The token will contain the username and unique
    identifier for the client as well as optional user which is being
    impersonated."""

    time_now = datetime.datetime.now(datetime.timezone.utc)

    issued_at = int(time_now.timestamp())

    if expires_at is None:
        expires_at = int(
            (time_now + datetime.timedelta(hours=TOKEN_EXPIRATION)).timestamp()
        )

    issuer = str(request.url.with_path("/").with_query(None))

    jwt_data = {
        "iss": issuer,
        "sub": client.name,
        "jti": client.identity,
        "iat": issued_at,
        "exp": expires_at,
    }

    if user:
        jwt_data["act"] = {"sub": user}

    jwt_token = jwt.encode(
        jwt_data,
        jwt_token_secret(),
        algorithm="HS256",
    )

    return {
        "access_token": jwt_token,
        "token_type": "Bearer",
        "expires_at": expires_at,
    }


def decode_client_token(issuer: str, token: str, secret: str = None) -> dict:
    """Decode the client token and return the decoded token. If the token is
    invalid, an exception will be raised."""

    if not secret:
        secret = jwt_token_secret()

    return jwt.decode(token, secret, algorithms=["HS256"], issuer=issuer)


@web.middleware
async def jwt_token_middleware(
    request: web.Request, handler: Callable[..., web.Response]
) -> web.Response:
    """Extract and decode the JWT token from the Authorization header, if
    present. Store the decoded details in the request object for later use by
    decorators on the individual request handlers that need to authenticate the
    client and check for required authorization.
    """

    # Extract the Authorization header from the request if present.

    authorization = request.headers.get("Authorization")

    if authorization:
        # Check if the Authorization header is a Bearer token.

        parts = authorization.split()

        if len(parts) != 2:
            return web.Response(text="Invalid Authorization header", status=400)

        if parts[0].lower() != "bearer":
            return web.Response(text="Invalid Authorization header", status=400)

        # Decode the JWT token passed in the Authorization header.

        try:
            token = parts[1]
            issuer = str(request.url.with_path("/").with_query(None))
            decoded_token = decode_client_token(issuer, token)
        except jwt.ExpiredSignatureError:
            return web.Response(text="JWT token has expired", status=401)
        except jwt.InvalidTokenError:
            return web.Response(text="JWT token is invalid", status=401)

        # Store the decoded token in the request object for later use.

        request["jwt_token"] = decoded_token
        request["client_name"] = decoded_token["sub"]

    # Continue processing the request.

    return await handler(request)


def login_required(handler: Callable[..., web.Response]) -> web.Response:
    """Decorator to verify that client is logged in to the service."""

    async def wrapper(request: web.Request) -> web.Response:
        # Check if the decoded JWT token is present in the request object.

        if "jwt_token" not in request:
            return web.Response(text="JWT token not supplied", status=400)

        decoded_token = request["jwt_token"]

        # Check the client database for the client by the name of the client
        # taken from the JWT token subject. Then check if the identity of the
        # client is still the same as the one recorded in the JWT token.

        service_state = request.app["service_state"]
        client_database = service_state.client_database

        client = client_database.get_client(decoded_token["sub"])

        if not client:
            return web.Response(text="Client details not found", status=401)

        if not client.validate_identity(decoded_token["jti"]):
            return web.Response(text="Client identity does not match", status=401)

        if not client.validate_time_window(decoded_token.get("iat", 0)):
            return web.Response(text="Token issued outside time window", status=401)

        request["remote_client"] = client

        # Continue processing the request.

        return await handler(request)

    return wrapper


def roles_accepted(
    *roles: str,
) -> Callable[[Callable[..., web.Response]], web.Response]:
    """Decorator to check that the client has access to the endpoint by
    confirming that is has any role required by the endpoint for access."""

    def decorator(handler: Callable[..., web.Response]) -> web.Response:
        async def wrapper(request: web.Request) -> web.Response:
            # Check if the client has one of the required roles.

            client = request["remote_client"]

            matched_roles = client.has_required_role(*roles)

            if not matched_roles:
                return web.Response(text="Client access not permitted", status=403)

            request["client_roles"] = matched_roles

            # Continue processing the request.

            return await handler(request)

        return wrapper

    return decorator


async def api_auth_login(request: web.Request) -> web.Response:
    """Login handler for accessing the web application. Validates the username
    and password provided in the request and returns a JWT token if the
    credentials are valid."""

    # Extract the username and password from the request POST data.

    data = await request.json()

    username = data.get("username")
    password = data.get("password")

    if username is None:
        return web.Response(text="No username provided", status=400)

    if password is None:
        return web.Response(text="No password provided", status=400)

    # Check if the password is correct for the username. We need to work out
    # whether the client is gated by normal password, or whether expect to
    # be supplied with a proxy token which delgates authority to an alternate
    # user.

    service_state = request.app["service_state"]
    client_database = service_state.client_database

    client = client_database.get_client(username)

    expires_at = None
    client_user = None

    if not client:
        return web.Response(text="Invalid username/password", status=401)

    if client.password:
        if client.check_password(password):
            # Generate a JWT token for the user and return it. The response is
            # bundle with the token type and expiration time so they can be used
            # by the client without needing to parse the actual JWT token.

            token = generate_login_response(request, client, expires_at)

            return web.json_response(token)

    if client.proxy:
        # Decode the proxy token. The token will use the "sub" field to store
        # the name of the user (email) that the token is for. The "exp" field
        # may store the expiration time for the token after which it will no
        # longer be accepted for login. The "nbf" field may store the time
        # before which the token is not valid.

        try:
            decoded_token = decode_client_token(client.issuer, password, client.proxy)

            # Verify that a user has been provided and copy the expiration
            # time from the proxy token if it is present so it can be used in
            # the session token.

            client_user = decoded_token.get("sub")

            if not client_user:
                return web.Response(text="Proxy token missing user", status=401)

            expires_at = decoded_token.get("exp")

        except jwt.exceptions.MissingRequiredClaimError:
            return web.Response(text="Missing required claim in proxy token", status=401)

        except jwt.InvalidIssuerError:
            return web.Response(text="Invalid proxy token issuer", status=401)

        except jwt.InvalidIssuedAtError:
            return web.Response(text="Proxy token issued in the future", status=401)

        except jwt.ImmatureSignatureError:
            return web.Response(text="Proxy token not yet active", status=401)

        except jwt.ExpiredSignatureError:
            return web.Response(text="Proxy has expired", status=401)

        except jwt.InvalidTokenError:
            return web.Response(text="Invalid proxy token", status=401)

        # Generate a JWT token for the user and return it. The response is
        # bundle with the token type and expiration time so they can be used
        # by the client without needing to parse the actual JWT token.

        token = generate_login_response(request, client, expires_at, client_user)

        return web.json_response(token)

    # Return that credentials are invalid.

    return web.Response(text="Invalid username/password", status=401)


async def api_auth_logout(request: web.Request) -> web.Response:
    """Logout handler for the web application. The client will be logged out
    and the JWT token will be invalidated."""

    # Check if the decoded JWT token is present in the request object.

    if "jwt_token" not in request:
        return web.Response(text="JWT token not supplied", status=400)

    decoded_token = request["jwt_token"]

    # Check the client database for the client by the name of the client
    # taken from the JWT token subject. Then check if the identity of the
    # client is still the same as the one recorded in the JWT token.

    service_state = request.app["service_state"]
    client_database = service_state.client_database

    client = client_database.get_client(decoded_token["sub"])

    if not client:
        return web.Response(text="Client details not found", status=401)

    if not client.validate_identity(decoded_token["jti"]):
        return web.Response(text="Client identity does not match", status=401)

    if not client.validate_time_window(decoded_token.get("iat", 0)):
        return web.Response(text="Token no longer valid", status=401)

    if decoded_token.get("act"):
        return web.Response(text="Logout not supported for proxy tokens", status=400)

    # Revoke the tokens issued to the client.

    client.revoke_tokens()

    return web.json_response({})


# Set up the middleware and routes for the authentication and authorization.

middlewares = [cors_allow_origin, jwt_token_middleware]

routes = [
    web.post("/login", api_auth_login),
    web.post("/auth/login", api_auth_login),
    web.post("/auth/logout", api_auth_logout),
    web.get("/auth/verify", login_required(lambda r: web.json_response({}))),
]
