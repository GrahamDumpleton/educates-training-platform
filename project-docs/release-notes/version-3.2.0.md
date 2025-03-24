Version 3.2.0
=============

New Features
------------

* Added `--hostname` option for overridding generated hostname when creating a
  portal using the `educates create-portal` command. If only a single host name
  is given, the existing cluster ingress domain will still be added. If a fully
  qualified domain name is given it will be used as is.

* Added `--image-repository` option to set the default image repository to be
  used used by all workshops, unless overridden for a specific workshop, when
  creating a portal using the `educates create-portal` command.

* User details from the training portal are now saved to a `Secret` stored in
  the workshop namespace for each session, with a name of the form
  `$(session_name)-user`. Attributes are `username`, `first_name`, `last_name`
  and `email`. The secret can be used as a volume or as source of environment
  variables for the workshop session container, with caveat that since the
  secret is only available at the point a workshop session is allocated, it
  should not be used with reserved sessions. These are also available to use as
  data variables in `request.objects`.

Features Changed
----------------

* Workshop base images were updated to Fedora 41. This has also resulted in the
  Python version being updated to 3.13.

* Versions of `kubectl` provided in the workshop image are now 1.30, 1.31 and
  1.32. From now on the intent is that only clients for supported Kubernetes
  versions will be included. The `kubectl-convert` plugin is now also included.

* Updated `kind` version bundled with `educates` CLI. Default Kubernetes cluster
  version now created by `educates create-cluster` command will be 1.32.

* Updated versions of numerous bundled applications, including Contour, Docker,
  Docker Registry, Helm, Hugo, Carvel tools, `dive`, `yq`, `k9s`, `skaffold`,
  `kustomize`, `reveal.js`.

* Update bundled VS Code Server to version 1.97.2.

Bugs Fixed
----------

* When using a touch device such as iPhone/iPad and a clickable action was run,
  the on screen keyboard would pop up when not desriable. The keyboard is now
  not displayed, but the terminal the clickable action was running a command in
  or where text was pasted, will still show as having had focus.

* The `secure` property was missing in the `Workshop` CRD for `ingresses` even
  though was documented that existed.

* When proxying in the workshop gateway process, the HTTP `Host` header was
  sent in lower case. This is allowed by HTTP specification as meant to be case
  insensitive, but some web services were only accepting mixed case, so use the
  mixed case convention so better chance of working with broken web services.

* Password for `git` application server was not unique per workshop session but
  was the same for all workshop sessions within the workshop environment. The
  `git` credentials therefore only differed based on `git` username, which was
  predictable as was based on workshop session name.
