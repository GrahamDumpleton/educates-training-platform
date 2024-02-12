from .helpers import xget, Applications


def console_workshop_spec_patches(workshop_spec, console_properties):
    # If a virtual cluster is being used we will need to create a console per
    # workshop session rather than a single shared console instance for the
    # workshop environment. We deal with this in the vcluster application.

    applications = Applications(workshop_spec["session"].get("applications", {}))

    if applications.is_enabled("vcluster"):
        return {}

    # We only support the Kubernetes console at the moment so we can return
    # early if the console vendor is not Kubernetes.

    console_vendor = xget(console_properties, "console.vendor", "kubernetes")

    if console_vendor != "kubernetes":
        return {}

    # We need to add an ingress to the workshop defintion for the shared
    # Kubernetes web console. Note that we do not add a dashboard for the
    # console here and we instead rely on the fact that "ENABLE_CONSOLE" is set
    # in the environment variables of the workshop container and the workshop
    # web interface adds the dashboard for the console if this environment
    # variable is set. It has to be done this way due to ordering of dashboard
    # tabs being calculated in the workshop web interface.

    return {
        "spec": {
            "session": {
                "ingresses": [
                    {
                        "name": "console",
                        "host": "kubernetes-dashboard-web.$(workshop_namespace).svc.$(cluster_domain)",
                        "port": 8443,
                        "protocol": "https",
                        "secure": False,
                        "headers": [
                            {
                                "name": "Authorization",
                                "value": "Bearer $(kubernetes_token)",
                            },
                        ],
                    },
                ],
            },
        },
    }


def console_environment_objects_list(workshop_spec, console_properties):
    # If a virtual cluster is being used we will need to create a console per
    # workshop session rather than a single shared console instance for the
    # workshop environment. We deal with this in the vcluster application.

    applications = Applications(workshop_spec["session"].get("applications", {}))

    if applications.is_enabled("vcluster"):
        return []

    # We only support the Kubernetes console at the moment so we can return
    # early if the console vendor is not Kubernetes.

    console_vendor = xget(console_properties, "console.vendor", "kubernetes")

    if console_vendor != "kubernetes":
        return []

    # We only need a single Kubernetes dashboard instance for the workshop
    # environment as each workshop session will supply its own Kubernetes token
    # by injection of an "Authorization" header when proxying to the instance of
    # the Kubernetes dashboard.
    #
    # Note that we are using Kubernetes dashboard 2.7.x at present. When 3.0.x
    # is released we will need to create an additional deployment and service
    # as the API proxy has been split out from the web server hosting the front
    # end. At the same time the ingress definition will need to be update to
    # split out requests against "/api" URL path to the separate API service.

    return [
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "kubernetes-dashboard",
                "namespace": "$(workshop_namespace)",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "kubernetes-dashboard-csrf",
                "namespace": "$(workshop_namespace)",
            },
            "type": "Opaque",
            "data": {"csrf": ""},
        },
        {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": "kubernetes-dashboard-key-holder",
                "namespace": "$(workshop_namespace)",
            },
            "type": "Opaque",
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "kubernetes-dashboard-settings",
                "namespace": "$(workshop_namespace)",
            },
        },
        {
            "kind": "Role",
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "metadata": {
                "name": "kubernetes-dashboard",
                "namespace": "$(workshop_namespace)",
            },
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": ["secrets"],
                    "resourceNames": [
                        "kubernetes-dashboard-key-holder",
                        "kubernetes-dashboard-csrf",
                    ],
                    "verbs": ["get", "update", "delete"],
                },
                {
                    "apiGroups": [""],
                    "resources": ["configmaps"],
                    "resourceNames": ["kubernetes-dashboard-settings"],
                    "verbs": ["get", "update"],
                },
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": "kubernetes-dashboard",
                "namespace": "$(workshop_namespace)",
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "Role",
                "name": "kubernetes-dashboard",
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "kubernetes-dashboard",
                    "namespace": "$(workshop_namespace)",
                }
            ],
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "kubernetes-dashboard-web",
                "namespace": "$(workshop_namespace)",
                "labels": {
                    "app.kubernetes.io/name": "kubernetes-dashboard-web",
                    "app.kubernetes.io/part-of": "kubernetes-dashboard",
                    "app.kubernetes.io/component": "web",
                },
            },
            "spec": {
                "ports": [{"name": "web", "port": 8443}],
                "selector": {
                    "app.kubernetes.io/name": "kubernetes-dashboard-web",
                    "app.kubernetes.io/part-of": "kubernetes-dashboard",
                },
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "kubernetes-dashboard-web",
                "namespace": "$(workshop_namespace)",
                "labels": {
                    "app.kubernetes.io/name": "kubernetes-dashboard-web",
                    "app.kubernetes.io/part-of": "kubernetes-dashboard",
                    "app.kubernetes.io/component": "web",
                },
            },
            "spec": {
                "replicas": 1,
                "revisionHistoryLimit": 10,
                "selector": {
                    "matchLabels": {
                        "app.kubernetes.io/name": "kubernetes-dashboard-web",
                        "app.kubernetes.io/part-of": "kubernetes-dashboard",
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app.kubernetes.io/name": "kubernetes-dashboard-web",
                            "app.kubernetes.io/part-of": "kubernetes-dashboard",
                            "app.kubernetes.io/component": "web",
                        }
                    },
                    "spec": {
                        "securityContext": {
                            "runAsNonRoot": True,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "kubernetes-dashboard-web",
                                "image": "docker.io/kubernetesui/dashboard:v2.7.0",
                                "imagePullPolicy": "IfNotPresent",
                                "args": [
                                    "--namespace=$(workshop_namespace)",
                                    "--auto-generate-certificates",
                                    "--enable-insecure-login=false",
                                    "--metrics-provider=none",
                                ],
                                "ports": [
                                    {
                                        "containerPort": 8443,
                                        "name": "web",
                                        "protocol": "TCP",
                                    }
                                ],
                                "volumeMounts": [
                                    {"mountPath": "/tmp", "name": "tmp-volume"}
                                ],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "runAsUser": 1001,
                                    "runAsGroup": 2001,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                            }
                        ],
                        "volumes": [{"name": "tmp-volume", "emptyDir": {}}],
                        "serviceAccountName": "kubernetes-dashboard",
                    },
                },
            },
        },
    ]


def console_session_objects_list(workshop_spec, console_properties):
    # If a virtual cluster is being used we will need to create a console per
    # workshop session rather than a single shared console instance for the
    # workshop environment. We deal with this in the vcluster application.

    applications = Applications(workshop_spec["session"].get("applications", {}))

    if applications.is_enabled("vcluster"):
        return []

    # We only support the Kubernetes console at the moment so we can return
    # early if the console vendor is not Kubernetes.

    console_vendor = xget(console_properties, "console.vendor", "kubernetes")

    if console_vendor != "kubernetes":
        return []

    return []


def console_pod_template_spec_patches(workshop_spec, console_properties):
    # If a virtual cluster is being used we will need to create a console per
    # workshop session rather than a single shared console instance for the
    # workshop environment. We deal with this in the vcluster application.

    applications = Applications(workshop_spec["session"].get("applications", {}))

    if applications.is_enabled("vcluster"):
        return {}

    # We only support the Kubernetes console at the moment so we can return
    # early if the console vendor is not Kubernetes.

    console_vendor = xget(console_properties, "console.vendor", "kubernetes")

    if console_vendor != "kubernetes":
        return {}

    # We need to add environment variables to the workshop container to enable
    # the console tab in the workshop dashboard and specify the URL for how to
    # access the console.

    return {
        "containers": [
            {
                "name": "workshop",
                "env": [
                    {
                        "name": "ENABLE_CONSOLE",
                        "value": "true",
                    },
                    {
                        "name": "CONSOLE_VENDOR",
                        "value": "kubernetes",
                    },
                    {
                        "name": "CONSOLE_URL",
                        "value": "$(ingress_protocol)://console-$(session_name).$(ingress_domain)$(ingress_port_suffix)/#/overview/?namespace=$(session_namespace)",
                    },
                ],
            },
        ],
    }
