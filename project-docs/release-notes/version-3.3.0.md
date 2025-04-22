Version 3.3.0
=============

New Features
------------

* Added `local resolver update` CLI command to reload Resolver container in 
  case there's a change in local ip assigned to the computer running educates
  local.

* It is now possible via the REST API of the training portal and lookup service,
  when requesting a workshop, to provide a webhook URL to which analytics events
  pertaining to just that workshop session should be delivered.

Bugs Fixed
----------

* When the lookup service was being deployed and an insecure ingress was being
  used to access it, clients were being incorrectly redirected to a secure
  ingress, resulted in an error since only insecure access was being expected.

* When deploying a workshop to a local docker environment using the `educates`
  CLI it would fail if the local registry hadn't previously been deployed as it
  was trying to map the docker network for the registry when not required.

* The URL to which a users browser was redirected when the workshop session was
  completed was stored as a browser cookie. This caused issues when interacting
  with a training portal via a custom front end portal using the training portal
  REST API. In this case if you had multiple workshop sessions running and they
  had each defined different URLs to redirect to, the workshop session which was
  created second would override the expected destination for the first workshop
  session. Instead of using a session cookie the URL for location to redirect to
  at the end of a workshop session is now stored along with the details of the
  session in the training portal database and that is used to determine where to
  redirect the users browser at the end of a workshop session.
