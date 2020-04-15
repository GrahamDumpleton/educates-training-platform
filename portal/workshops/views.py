import os
import datetime
import random
import string

import wrapt

from django.shortcuts import render, redirect, reverse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth import login

from oauth2_provider.views.generic import ProtectedResourceView
from oauth2_provider.decorators import protected_resource

from .models import Environment, Session, Workshop
from .manager import initiate_workshop_session, scheduler

portal_name = os.environ.get("TRAINING_PORTAL", "")
ingress_domain = os.environ.get("INGRESS_DOMAIN", "training.eduk8s.io")
ingress_secret = os.environ.get("INGRESS_SECRET", "")
ingress_protocol = os.environ.get("INGRESS_PROTOCOL", "http")

@login_required
def catalog(request):
    catalog = []

    notification = request.GET.get('notification', '')

    for environment in Environment.objects.all().order_by('name'):
        details = {}
        details['environment'] = environment.name
        details['workshop'] = environment.workshop

        available = max(0, environment.capacity - Session.objects.filter(
                environment=environment, allocated=True, state="running").count())
        details['available'] = available

        if notification != "session-deleted":
            sessions = environment.session_set.filter(allocated=True, state="running", owner=request.user)
            details['session'] = sessions and sessions[0] or None
        else:
            details['session'] = None

        catalog.append(details)

    context = {
        "catalog": catalog,
        "notification": request.GET.get('notification', '')
    }

    return render(request, 'workshops/catalog.html', context)

@protected_resource()
def catalog_environments(request):
    catalog = []

    for environment in Environment.objects.all().order_by('name'):
        details = {}

        details['name'] = environment.name

        details['workshop'] = {
            'name': environment.workshop.name,
            'vendor': environment.workshop.vendor,
            'title': environment.workshop.title,
            'description': environment.workshop.description,
            'url': environment.workshop.url,
        }

        details['duration'] = environment.duration

        details['capacity'] = environment.capacity
        details['reserved'] = environment.reserved

        details['allocated'] = Session.objects.filter(environment=environment,
                allocated=True, state="running").count()
        details['available'] = Session.objects.filter(environment=environment,
                allocated=False, state__in=["starting", "running"]).count()

        catalog.append(details)

    return JsonResponse({"environments": catalog})

@login_required
@wrapt.synchronized(scheduler)
@transaction.atomic
def environment(request, name):
    context = {}

    # Ensure there is an environment which the specified name in existance.

    try:
         environment = Environment.objects.get(name=name)
    except Environment.DoesNotExist:
        return redirect(reverse('workshops_catalog')+'?notification=workshop-invalid')

    # Determine if there is already an allocated session which the current
    # user is an owner of.

    session = None

    sessions = environment.session_set.filter(allocated=True, state="running",
            owner=request.user)

    if not sessions:
        # Allocate a session by getting all the sessions which have not
        # been allocated and allocate one.

        sessions = environment.session_set.filter(allocated=False, state="running")

        if sessions:
            session = sessions[0]

            session.owner = request.user
            session.allocated = True

            session.started = timezone.now()

            if environment.duration:
                session.expires = (session.started +
                        datetime.timedelta(seconds=environment.duration))

            # If required to have spare workshop instance, unless we
            # have reached capacity, initiate creation of a new session
            # to replace the one we just allocated.

            reserved_sessions = Session.objects.filter(environment=name,
                    state__in=["starting", "running"], allocated=False)

            if environment.reserved and reserved_sessions.count()-1 < environment.reserved:
                active_sessions = Session.objects.filter(environment=environment,
                        state__in=["starting", "running"])

                if active_sessions.count() < environment.capacity:
                    replacement_session = initiate_workshop_session(environment)
                    transaction.on_commit(lambda: scheduler.create_workshop_session(
                            name=replacement_session.name))

            session.save()

        else:
            # No session available. If there is still capacity,
            # then initiate creation of a new session and use it. We
            # shouldn't really get here if required to have spare
            # workshop instances unless capacity had been reached as
            # the spares should always have been topped up.

            active_sessions = Session.objects.filter(environment=environment,
                    state__in=["starting", "running"])

            if active_sessions.count() < environment.capacity:
                session = initiate_workshop_session(environment)
                transaction.on_commit(lambda: scheduler.create_workshop_session(
                        name=session.name))

                session.owner = request.user
                session.allocated = True

                session.started = timezone.now()

                if environment.duration:
                    session.expires = (session.started +
                            datetime.timedelta(seconds=environment.duration))

                session.save()

                environment.save()

    else:
        session = sessions[0]

    if session:
        return redirect('workshops_session', name=session.name)

    return redirect(reverse('workshops_catalog')+'?notification=session-unavailable')

@protected_resource()
@wrapt.synchronized(scheduler)
@transaction.atomic
def environment_request(request, name):
    # Only allow user who is staff to request session.

    if not request.user.is_staff:
        return HttpResponseForbidden("Session requests not permitted")

    # Ensure there is an environment which the specified name in existance.

    try:
         environment = Environment.objects.get(name=name)
    except Environment.DoesNotExist:
        return HttpResponseForbidden("Environment does not exist")

    # Extract required parameters for creating the session.

    redirect_url = request.GET['redirect_url']

    if not redirect_url:
        return HttpResponseBadRequest("Need redirect URL for session end")

    # Allocate a session by getting all the sessions which have not
    # been allocated and allocate one.

    characters = string.ascii_letters + string.digits
    user_tag = "".join(random.sample(characters, 5))
    access_token = "".join(random.sample(characters, 32))

    sessions = environment.session_set.filter(allocated=False, state="running")

    if sessions:
        session = sessions[0]

        user = User.User.objects.create_user(f"{session.name}-{user_tag}")

        session.owner = user
        session.anonymous = True
        session.token = access_token
        session.allocated = True

        session.started = timezone.now()

        if environment.duration:
            session.expires = (session.started +
                    datetime.timedelta(seconds=environment.duration))

        # If required to have spare workshop instance, unless we
        # have reached capacity, initiate creation of a new session
        # to replace the one we just allocated.

        reserved_sessions = Session.objects.filter(environment=name,
                state__in=["starting", "running"], allocated=False)

        if environment.reserved and reserved_sessions.count()-1 < environment.reserved:
            active_sessions = Session.objects.filter(environment=environment,
                    state__in=["starting", "running"])

            if active_sessions.count() < environment.capacity:
                replacement_session = initiate_workshop_session(environment)
                transaction.on_commit(lambda: scheduler.create_workshop_session(
                        name=replacement_session.name))

        session.save()

    else:
        # No session available. If there is still capacity,
        # then initiate creation of a new session and use it. We
        # shouldn't really get here if required to have spare
        # workshop instances unless capacity had been reached as
        # the spares should always have been topped up.

        active_sessions = Session.objects.filter(environment=environment,
                state__in=["starting", "running"])

        if active_sessions.count() < environment.capacity:
            session = initiate_workshop_session(environment)
            transaction.on_commit(lambda: scheduler.create_workshop_session(
                    name=session.name))

            user = User.User.objects.create_user(f"{session.name}-{user_tag}")

            session.owner = user
            session.anonymous = True
            session.token = access_token
            session.allocated = True

            session.owner = user
            session.anonymous = True
            session.token = access_token
            session.allocated = True

            session.started = timezone.now()

            if environment.duration:
                session.expires = (session.started +
                        datetime.timedelta(seconds=environment.duration))

            session.save()

            environment.save()

        else:
            return JSONResponse({"error": "No session available"})

    details = {}

    details["session"] = session.name
    details["url"] = reverse('session_activate')+f'?token={session.token}'

    return JSONResponse(details)

@login_required
@wrapt.synchronized(scheduler)
@transaction.atomic
def session(request, name):
    context = {}

    # Ensure there is allocated session for the user.

    try:
        session = Session.objects.get(name=name, allocated=True,
                owner=request.user)
    except Session.DoesNotExist:
        return redirect(reverse('workshops_catalog')+'?notification=session-invalid')

    context['session'] = session
    context['session_url'] = f'{ingress_protocol}://{session.name}.{ingress_domain}'

    return render(request, 'workshops/session.html', context)

def session_activate(request, name):
    access_token = request.GET.get('token')

    if not access_token:
        return HttpResponseBadRequest("No access token supplied")

    try:
        session = Session.objects.get(name=name, allocated=True)
    except Session.DoesNotExist:
        return HttpResponseBadRequest("Invalid session name supplied")

    if session.token != access_token:
        return HttpResponseBadRequest("Invalid access token for session")

    if not session.owner:
        return HttpResponseServerError("No owner defined for session")

    if not session.owner.is_active:
        return HttpResponseServerError("Owner for session is not active")

    login(request, session.user)

    return redirect('workshops_session', name=session.name)

@login_required
@wrapt.synchronized(scheduler)
@transaction.atomic
def session_delete(request, name):
    context = {}

    # Ensure there is allocated session for the user.

    try:
         session = Session.objects.get(name=name, allocated=True,
                 owner=request.user)
    except Session.DoesNotExist:
        return redirect(reverse('workshops_catalog')+'?notification=session-invalid')

    scheduler.delete_workshop_session(session)

    if session.redirect:
        return redirect(session.redirect)

    return redirect(reverse('workshops_catalog')+'?notification=session-deleted')

@protected_resource()
def session_authorize(request, name):
    # Ensure that the session exists.

    try:
         session = Session.objects.get(name=name)
    except Session.DoesNotExist:
        raise Http404("Session does not exist")

    # Check that session is allocated and in use.

    if not session.allocated:
        return HttpResponseForbidden("Session is not currently in use")

    # Check that are owner of session, or a staff member.

    if not request.user.is_staff:
        if session.owner != request.user:
            return HttpResponseForbidden("Access to session not permitted")

    return JsonResponse({"owner": session.owner.username})

@protected_resource(scopes=['user:info'])
def session_schedule(request, name):
    # Ensure that the session exists.

    try:
         session = Session.objects.get(name=name)
    except Session.DoesNotExist:
        raise Http404("Session does not exist")

    # Check that session is allocated and in use.

    if not session.allocated:
        return HttpResponseForbidden("Session is not currently in use")

    # Check that are owner of session, or a staff member.

    if not request.user.is_staff:
        if session.owner != request.user:
            return HttpResponseForbidden("Access to session not permitted")

    details = {}

    details["started"] = session.started
    details["expires"] = session.expires

    if session.expires:
        now = timezone.now()
        if session.expires > now:
            details["countdown"] = int((session.expires-now).total_seconds())
        else:
            details["countdown"] = 0

    return JsonResponse(details)

@protected_resource(scopes=['user:info'])
def session_extend(request, name):
    # Ensure that the session exists.

    try:
         session = Session.objects.get(name=name)
    except Session.DoesNotExist:
        raise Http404("Session does not exist")

    # Check that session is allocated and in use.

    if not session.allocated:
        return HttpResponseForbidden("Session is not currently in use")

    # Check that are owner of session, or a staff member.

    if not request.user.is_staff:
        if session.owner != request.user:
            return HttpResponseForbidden("Access to session not permitted")

    # Only extend if within the last five miniutes. Extend
    # for only an extra five minutes.

    if session.expires:
        now = timezone.now()
        remaining = (session.expires - now).total_seconds()
        if remaining > 0 and remaining <= 300:
            session.expires = session.expires + datetime.timedelta(seconds=300)
            session.save()

    details = {}

    details["started"] = session.started
    details["expires"] = session.expires

    if session.expires:
        now = timezone.now()
        if session.expires > now:
            details["countdown"] = int((session.expires-now).total_seconds())
        else:
            details["countdown"] = 0

    return JsonResponse(details)
