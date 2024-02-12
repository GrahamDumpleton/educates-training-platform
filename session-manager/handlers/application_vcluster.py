import yaml

from .helpers import xget, smart_overlay_merge, Applications

from .operator_config import (
    OPERATOR_API_GROUP,
    CLUSTER_STORAGE_GROUP,
    RANCHER_K3S_V1_25_IMAGE,
    RANCHER_K3S_V1_26_IMAGE,
    RANCHER_K3S_V1_27_IMAGE,
    RANCHER_K3S_V1_28_IMAGE,
    LOFTSH_VCLUSTER_IMAGE,
    CONTOUR_BUNDLE_IMAGE,
)


K8S_DEFAULT_VERSION = "1.27"

K3S_VERSIONS = {
    "1.25": RANCHER_K3S_V1_25_IMAGE,
    "1.26": RANCHER_K3S_V1_26_IMAGE,
    "1.27": RANCHER_K3S_V1_27_IMAGE,
    "1.28": RANCHER_K3S_V1_28_IMAGE,
}


def vcluster_workshop_spec_patches(workshop_spec, vcluster_properties):
    policy = xget(workshop_spec, "session.namespaces.security.policy", "baseline")

    workshop_patch = {
        "spec": {
            "session": {
                "namespaces": {
                    "security": {"policy": policy, "token": {"enabled": False}}
                },
                "variables": [
                    {
                        "name": "vcluster_secret",
                        "value": "$(session_namespace)-vc-kubeconfig",
                    },
                    {
                        "name": "vcluster_namespace",
                        "value": "$(session_namespace)-vc",
                    },
                ],
            }
        }
    }

    # If the console is enabled we need to add an ingress to the workshop
    # defintion for the shared Kubernetes web console which routes to port
    # 10083, which will be used by the Kubernetes dashboard running in the side
    # car container. Note that we do not add a dashboard for the console here
    # and we instead rely on the fact that "ENABLE_CONSOLE" is set in the
    # environment variables of the workshop container and the workshop web
    # interface adds the dashboard for the console if this environment variable
    # is set. It has to be done this way due to ordering of dashboard tabs being
    # calculated in the workshop web interface.

    applications = Applications(workshop_spec["session"].get("applications", {}))

    if applications.is_enabled("console"):
        console_properties = applications.properties("console")

        if xget(console_properties, "vendor", "kubernetes") == "kubernetes":
            smart_overlay_merge(
                workshop_patch,
                {
                    "spec": {
                        "session": {
                            "ingresses": [
                                {
                                    "name": "console",
                                    "port": 10083,
                                },
                            ],
                        },
                    },
                },
            )

    return workshop_patch


def vcluster_environment_objects_list(workshop_spec, vcluster_properties):
    return []


COREDNS_YAML = """
apiVersion: v1
kind: ServiceAccount
metadata:
  name: coredns
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  labels:
    kubernetes.io/bootstrapping: rbac-defaults
  name: system:coredns
rules:
  - apiGroups:
      - ""
    resources:
      - endpoints
      - services
      - pods
      - namespaces
    verbs:
      - list
      - watch
  - apiGroups:
      - discovery.k8s.io
    resources:
      - endpointslices
    verbs:
      - list
      - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  annotations:
    rbac.authorization.kubernetes.io/autoupdate: "true"
  labels:
    kubernetes.io/bootstrapping: rbac-defaults
  name: system:coredns
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: system:coredns
subjects:
  - kind: ServiceAccount
    name: coredns
    namespace: kube-system
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: coredns
  namespace: kube-system
data:
  Corefile: |
    .:1053 {
        {{.LOG_IN_DEBUG}}
        errors
        health
        ready
        kubernetes cluster.local in-addr.arpa ip6.arpa {
          pods insecure
          fallthrough in-addr.arpa ip6.arpa
        }
        hosts /etc/coredns/NodeHosts {
          ttl 60
          reload 15s
          fallthrough
        }
        prometheus :9153
        forward . /etc/resolv.conf
        cache 30
        loop
        reload
        loadbalance
    }

    import /etc/coredns/custom/*.server
  NodeHosts: ""
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: coredns
  namespace: kube-system
  labels:
    k8s-app: kube-dns
    kubernetes.io/name: "CoreDNS"
spec:
  replicas: 1
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
  selector:
    matchLabels:
      k8s-app: kube-dns
  template:
    metadata:
      labels:
        k8s-app: kube-dns
    spec:
      priorityClassName: "system-cluster-critical"
      serviceAccountName: coredns
      nodeSelector:
        kubernetes.io/os: linux
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              k8s-app: kube-dns
      containers:
        - name: coredns
          image: {{.IMAGE}}
          imagePullPolicy: IfNotPresent
          resources:
            limits:
              cpu: 1000m
              memory: 170Mi
            requests:
              cpu: 3m
              memory: 16Mi
          args: [ "-conf", "/etc/coredns/Corefile" ]
          volumeMounts:
            - name: config-volume
              mountPath: /etc/coredns
              readOnly: true
            - name: custom-config-volume
              mountPath: /etc/coredns/custom
              readOnly: true
          ports:
            - containerPort: 1053
              name: dns
              protocol: UDP
            - containerPort: 1053
              name: dns-tcp
              protocol: TCP
            - containerPort: 9153
              name: metrics
              protocol: TCP
          securityContext:
            runAsUser: {{.RUN_AS_USER}}
            runAsNonRoot: {{.RUN_AS_NON_ROOT}}
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
            readOnlyRootFilesystem: true
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
              scheme: HTTP
            initialDelaySeconds: 60
            periodSeconds: 10
            timeoutSeconds: 1
            successThreshold: 1
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8181
              scheme: HTTP
            initialDelaySeconds: 0
            periodSeconds: 2
            timeoutSeconds: 1
            successThreshold: 1
            failureThreshold: 3
      dnsPolicy: Default
      volumes:
        - name: config-volume
          configMap:
            name: coredns
            items:
              - key: Corefile
                path: Corefile
              - key: NodeHosts
                path: NodeHosts
        - name: custom-config-volume
          configMap:
            name: coredns-custom
            optional: true
---
apiVersion: v1
kind: Service
metadata:
  name: kube-dns
  namespace: kube-system
  annotations:
    prometheus.io/port: "9153"
    prometheus.io/scrape: "true"
  labels:
    k8s-app: kube-dns
    kubernetes.io/cluster-service: "true"
    kubernetes.io/name: "CoreDNS"
spec:
  selector:
    k8s-app: kube-dns
  type: ClusterIP
  ports:
    - name: dns
      port: 53
      targetPort: 1053
      protocol: UDP
    - name: dns-tcp
      port: 53
      targetPort: 1053
      protocol: TCP
    - name: metrics
      port: 9153
      protocol: TCP
"""


def vcluster_session_objects_list(workshop_spec, vcluster_properties):
    syncer_memory = xget(vcluster_properties, "resources.syncer.memory", "1Gi")
    k3s_memory = xget(vcluster_properties, "resources.k3s.memory", "2Gi")

    syncer_storage = xget(vcluster_properties, "resources.syncer.storage", "5Gi")

    k8s_version = xget(vcluster_properties, "version", K8S_DEFAULT_VERSION)

    if k8s_version not in K3S_VERSIONS:
        k8s_version = K8S_DEFAULT_VERSION

    k3s_image = K3S_VERSIONS.get(k8s_version)

    ingress_enabled = xget(vcluster_properties, "ingress.enabled", False)

    ingress_subdomains = xget(vcluster_properties, "ingress.subdomains", [])
    ingress_subdomains = sorted(ingress_subdomains + ["default"])

    sync_resources = "hoststorageclasses,-ingressclasses"

    if ingress_enabled:
        sync_resources = f"{sync_resources},-ingresses"
    else:
        sync_resources = f"{sync_resources},ingresses"

    vcluster_objects = xget(vcluster_properties, "objects", [])

    syncer_args = []

    syncer_args.append(f"--sync={sync_resources}")

    map_services_from_virtual = xget(vcluster_properties, "services.fromVirtual", [])

    for mapping in map_services_from_virtual:
        from_virtual = mapping["from"]
        to_host = mapping["to"]
        syncer_args.append(f"--map-virtual-service={from_virtual}={to_host}")

    map_services_from_host = xget(vcluster_properties, "services.fromHost", [])

    for mapping in map_services_from_host:
        from_host = mapping["from"]
        to_virtual = mapping["to"]
        syncer_args.append(f"--map-host-service={from_host}={to_virtual}")

    objects = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": "$(session_namespace)-vc",
                "annotations": {
                    "secretgen.carvel.dev/excluded-from-wildcard-matching": "",
                    f"training.{OPERATOR_API_GROUP}/session.role": "custom",
                    f"training.{OPERATOR_API_GROUP}/session.budget": "custom",
                    f"training.{OPERATOR_API_GROUP}/session.policy": "baseline",
                },
            },
        },
        {
            "apiVersion": f"secrets.{OPERATOR_API_GROUP}/v1beta1",
            "kind": "SecretCopier",
            "metadata": {"name": "$(session_namespace)-vc-kubeconfig"},
            "spec": {
                "rules": [
                    {
                        "sourceSecret": {
                            "name": "$(session_namespace)-vc-kubeconfig",
                            "namespace": "$(session_namespace)-vc",
                        },
                        "targetNamespaces": {
                            "nameSelector": {"matchNames": ["$(workshop_namespace)"]}
                        },
                        "targetSecret": {"name": "$(vcluster_secret)"},
                        "reclaimPolicy": "Delete",
                    }
                ]
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "vc-my-vcluster",
                "namespace": "$(session_namespace)-vc",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ServiceAccount",
            "metadata": {
                "name": "vc-workload-my-vcluster",
                "namespace": "$(session_namespace)",
            },
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRole",
            "metadata": {
                "name": "my-vcluster-$(session_namespace)-vc",
            },
            "rules": [
                {
                    "apiGroups": ["networking.k8s.io"],
                    "resources": ["ingressclasses"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["storage.k8s.io"],
                    "resources": ["storageclasses"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": [""],
                    "resources": ["services"],
                    "verbs": ["get", "list", "watch"],
                },
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {
                "name": "my-vcluster",
                "namespace": "$(session_namespace)-vc",
            },
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": [
                        "configmaps",
                        "secrets",
                        "services",
                        "pods",
                        "pods/attach",
                        "pods/portforward",
                        "pods/exec",
                        "endpoints",
                        "persistentvolumeclaims",
                    ],
                    "verbs": [
                        "create",
                        "delete",
                        "patch",
                        "update",
                        "get",
                        "list",
                        "watch",
                    ],
                },
                {
                    "apiGroups": [""],
                    "resources": ["events", "pods/log"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["networking.k8s.io"],
                    "resources": ["ingresses"],
                    "verbs": [
                        "create",
                        "delete",
                        "patch",
                        "update",
                        "get",
                        "list",
                        "watch",
                    ],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": ["statefulsets", "replicasets", "deployments"],
                    "verbs": ["get", "list", "watch"],
                },
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": "my-vcluster",
                "namespace": "$(session_namespace)-vc",
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "vc-my-vcluster",
                    "namespace": "$(session_namespace)-vc",
                }
            ],
            "roleRef": {
                "kind": "Role",
                "name": "my-vcluster",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "Role",
            "metadata": {
                "name": "my-vcluster",
                "namespace": "$(session_namespace)",
            },
            "rules": [
                {
                    "apiGroups": [""],
                    "resources": [
                        "configmaps",
                        "secrets",
                        "services",
                        "pods",
                        "pods/attach",
                        "pods/portforward",
                        "pods/exec",
                        "endpoints",
                        "persistentvolumeclaims",
                    ],
                    "verbs": [
                        "create",
                        "delete",
                        "patch",
                        "update",
                        "get",
                        "list",
                        "watch",
                    ],
                },
                {
                    "apiGroups": [""],
                    "resources": ["events", "pods/log"],
                    "verbs": ["get", "list", "watch"],
                },
                {
                    "apiGroups": ["networking.k8s.io"],
                    "resources": ["ingresses"],
                    "verbs": [
                        "create",
                        "delete",
                        "patch",
                        "update",
                        "get",
                        "list",
                        "watch",
                    ],
                },
                {
                    "apiGroups": ["apps"],
                    "resources": ["statefulsets", "replicasets", "deployments"],
                    "verbs": ["get", "list", "watch"],
                },
            ],
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": "my-vcluster",
                "namespace": "$(session_namespace)",
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "vc-my-vcluster",
                    "namespace": "$(session_namespace)-vc",
                }
            ],
            "roleRef": {
                "kind": "Role",
                "name": "my-vcluster",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        },
        {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "ClusterRoleBinding",
            "metadata": {
                "name": "my-vcluster-$(session_namespace)-vc",
            },
            "subjects": [
                {
                    "kind": "ServiceAccount",
                    "name": "vc-my-vcluster",
                    "namespace": "$(session_namespace)-vc",
                }
            ],
            "roleRef": {
                "kind": "ClusterRole",
                "name": "my-vcluster-$(session_namespace)-vc",
                "apiGroup": "rbac.authorization.k8s.io",
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "my-vcluster-init-manifests",
                "namespace": "$(session_namespace)-vc",
            },
            "data": {
                "manifests": yaml.dump_all(vcluster_objects, Dumper=yaml.Dumper),
            },
        },
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": "my-vcluster-coredns",
                "namespace": "$(session_namespace)-vc",
            },
            "data": {
                "coredns.yaml": COREDNS_YAML,
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "my-vcluster",
                "namespace": "$(session_namespace)-vc",
            },
            "spec": {
                "type": "ClusterIP",
                "ports": [
                    {
                        "name": "https",
                        "port": 443,
                        "targetPort": 8443,
                        "protocol": "TCP",
                    }
                ],
                "selector": {"app": "vcluster", "release": "my-vcluster"},
            },
        },
        {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": "my-vcluster-headless",
                "namespace": "$(session_namespace)-vc",
            },
            "spec": {
                "ports": [
                    {
                        "name": "https",
                        "port": 443,
                        "targetPort": 8443,
                        "protocol": "TCP",
                    }
                ],
                "clusterIP": "None",
                "selector": {"app": "vcluster", "release": "my-vcluster"},
            },
        },
        {
            "apiVersion": "apps/v1",
            "kind": "StatefulSet",
            "metadata": {
                "name": "my-vcluster",
                "namespace": "$(session_namespace)-vc",
            },
            "spec": {
                "serviceName": "my-vcluster-headless",
                "replicas": 1,
                "selector": {
                    "matchLabels": {"app": "vcluster", "release": "my-vcluster"}
                },
                "volumeClaimTemplates": [
                    {
                        "metadata": {"name": "data"},
                        "spec": {
                            "accessModes": ["ReadWriteOnce"],
                            "storageClassName": None,
                            "resources": {"requests": {"storage": syncer_storage}},
                        },
                    }
                ],
                "template": {
                    "metadata": {
                        "labels": {"app": "vcluster", "release": "my-vcluster"}
                    },
                    "spec": {
                        "terminationGracePeriodSeconds": 10,
                        "nodeSelector": {},
                        "affinity": {},
                        "tolerations": [],
                        "serviceAccountName": "vc-my-vcluster",
                        "volumes": [
                            {
                                "name": "config",
                                "emptyDir": {},
                            },
                            {
                                "name": "coredns",
                                "configMap": {
                                    "name": "my-vcluster-coredns",
                                },
                            },
                        ],
                        "securityContext": {
                            "fsGroup": CLUSTER_STORAGE_GROUP,
                            "supplementalGroups": [CLUSTER_STORAGE_GROUP],
                        },
                        "containers": [
                            {
                                "image": k3s_image,
                                "name": "vcluster",
                                "command": ["/bin/sh"],
                                "args": [
                                    "-c",
                                    "/bin/k3s server --write-kubeconfig=/data/k3s-config/kube-config.yaml --data-dir=/data --disable=traefik,servicelb,metrics-server,local-storage,coredns --disable-network-policy --disable-agent --disable-cloud-controller --flannel-backend=none --disable-scheduler --kube-controller-manager-arg=controllers=*,-nodeipam,-nodelifecycle,-persistentvolume-binder,-attachdetach,-persistentvolume-expander,-cloud-node-lifecycle,-ttl --kube-apiserver-arg=endpoint-reconciler-type=none --service-cidr=$(SERVICE_CIDR) && true",
                                ],
                                "env": [
                                    {
                                        "name": "SERVICE_CIDR",
                                        "valueFrom": {
                                            "configMapKeyRef": {
                                                "name": "vc-cidr-my-vcluster",
                                                "key": "cidr",
                                            }
                                        },
                                    },
                                ],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "runAsNonRoot": True,
                                    "runAsUser": 12345,
                                },
                                "volumeMounts": [
                                    {
                                        "name": "config",
                                        "mountPath": "/etc/rancher",
                                    },
                                    {"mountPath": "/data", "name": "data"},
                                ],
                                "resources": {
                                    "limits": {"memory": k3s_memory},
                                    "requests": {"cpu": "200m", "memory": k3s_memory},
                                },
                            },
                            {
                                "name": "syncer",
                                "image": LOFTSH_VCLUSTER_IMAGE,
                                "args": [
                                    "--name=my-vcluster",
                                    "--service-account=vc-workload-my-vcluster",
                                    "--target-namespace=$(session_namespace)",
                                    "--tls-san=my-vcluster.$(session_namespace)-vc.svc.cluster.local",
                                    "--out-kube-config-server=https://my-vcluster.$(session_namespace)-vc.svc.cluster.local",
                                    "--out-kube-config-secret=$(session_namespace)-vc-kubeconfig",
                                    "--kube-config-context-name=my-vcluster",
                                    "--leader-elect=false",
                                ]
                                + syncer_args,
                                "livenessProbe": {
                                    "httpGet": {
                                        "path": "/healthz",
                                        "port": 8443,
                                        "scheme": "HTTPS",
                                    },
                                    "failureThreshold": 60,
                                    "initialDelaySeconds": 60,
                                    "periodSeconds": 2,
                                },
                                "readinessProbe": {
                                    "httpGet": {
                                        "path": "/readyz",
                                        "port": 8443,
                                        "scheme": "HTTPS",
                                    },
                                    "failureThreshold": 60,
                                    "periodSeconds": 2,
                                },
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "runAsNonRoot": True,
                                    "runAsUser": 12345,
                                },
                                "env": [
                                    {
                                        "name": "POD_IP",
                                        "valueFrom": {
                                            "fieldRef": {"fieldPath": "status.podIP"}
                                        },
                                    },
                                    {
                                        "name": "VCLUSTER_NODE_NAME",
                                        "valueFrom": {
                                            "fieldRef": {"fieldPath": "spec.nodeName"}
                                        },
                                    },
                                ],
                                "volumeMounts": [
                                    {
                                        "name": "coredns",
                                        "mountPath": "/manifests/coredns",
                                        "readOnly": True,
                                    },
                                    {
                                        "mountPath": "/data",
                                        "name": "data",
                                        "readOnly": True,
                                    },
                                ],
                                "resources": {
                                    "limits": {"memory": syncer_memory},
                                    "requests": {
                                        "cpu": "100m",
                                        "memory": syncer_memory,
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        },
    ]

    if ingress_enabled:
        objects.extend(
            [
                {
                    "apiVersion": "v1",
                    "kind": "Secret",
                    "metadata": {
                        "name": "contour-values",
                        "namespace": "$(session_namespace)-vc",
                    },
                    "stringData": {
                        "values.yml": "envoy:\n  service:\n    type: ClusterIP"
                    },
                },
                {
                    "apiVersion": "kappctrl.k14s.io/v1alpha1",
                    "kind": "App",
                    "metadata": {
                        "name": "contour.community.tanzu.vmware.com.1.22.0",
                        "namespace": "$(session_namespace)-vc",
                    },
                    "spec": {
                        "cluster": {
                            "namespace": "default",
                            "kubeconfigSecretRef": {
                                "name": "$(vcluster_secret)",
                                "key": "config",
                            },
                        },
                        "fetch": [{"imgpkgBundle": {"image": CONTOUR_BUNDLE_IMAGE}}],
                        "template": [
                            {
                                "ytt": {
                                    "paths": ["config/"],
                                    "valuesFrom": [
                                        {"secretRef": {"name": "contour-values"}}
                                    ],
                                }
                            },
                            {"kbld": {"paths": ["-", ".imgpkg/images.yml"]}},
                        ],
                        "deploy": [{"kapp": {}}],
                        "noopDelete": True,
                        "syncPeriod": "24h",
                    },
                },
            ]
        )

        ingress_body = {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": "contour-$(session_namespace)",
                "namespace": "$(session_namespace)",
                "annotations": {
                    "nginx.ingress.kubernetes.io/proxy-send-timeout": "3600",
                    "nginx.ingress.kubernetes.io/proxy-read-timeout": "3600",
                    "projectcontour.io/websocket-routes": "/",
                    "projectcontour.io/response-timeout": "3600s",
                },
            },
            "spec": {
                "rules": [
                    {
                        "host": "*.$(session_namespace).$(ingress_domain)",
                        "http": {
                            "paths": [
                                {
                                    "path": "/",
                                    "pathType": "Prefix",
                                    "backend": {
                                        "service": {
                                            "name": "envoy-x-projectcontour-x-my-vcluster",
                                            "port": {"number": 80},
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ]
            },
        }

        for subdomain in filter(len, ingress_subdomains):
            ingress_body["spec"]["rules"].append(
                {
                    "host": f"*.{subdomain}.$(session_namespace).$(ingress_domain)",
                    "http": {
                        "paths": [
                            {
                                "path": "/",
                                "pathType": "Prefix",
                                "backend": {
                                    "service": {
                                        "name": "envoy-x-projectcontour-x-my-vcluster",
                                        "port": {"number": 80},
                                    }
                                },
                            }
                        ]
                    },
                }
            )

        objects.append(ingress_body)

    return objects


def vcluster_pod_template_spec_patches(workshop_spec, vcluster_properties):
    template_patch = {
        "containers": [
            {
                "name": "workshop",
                "volumeMounts": [
                    {"name": "kubeconfig", "mountPath": "/opt/kubeconfig"}
                ],
            },
        ],
        "volumes": [
            {
                "name": "kubeconfig",
                "secret": {"secretName": "$(vcluster_secret)"},
            }
        ],
    }

    # If console is enabled then we need to add environment variables to the
    # workshop container to enable the console tab in the workshop dashboard and
    # specify the URL for how to access the console. We also need to setup a
    # temporary volume for dashboard logs files.

    applications = Applications(workshop_spec["session"].get("applications", {}))

    if applications.is_enabled("console"):
        console_properties = applications.properties("console")

        if xget(console_properties, "vendor", "kubernetes") == "kubernetes":
            smart_overlay_merge(
                template_patch,
                {
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
                                    "value": "$(ingress_protocol)://console-$(session_name).$(ingress_domain)$(ingress_port_suffix)/#/overview/?namespace=default",
                                },
                            ],
                        },
                        {
                            "name": "kubernetes-dashboard-web",
                            "image": "docker.io/kubernetesui/dashboard:v2.7.0",
                            "imagePullPolicy": "IfNotPresent",
                            "args": [
                                "--insecure-port=10083",
                                "--bind-address=127.0.0.1",
                                "--enable-insecure-login=false",
                                "--metrics-provider=none",
                                "--kubeconfig=/opt/kubeconfig/config",
                            ],
                            "ports": [
                                {
                                    "containerPort": 10083,
                                    "name": "web",
                                    "protocol": "TCP",
                                }
                            ],
                            "volumeMounts": [
                                {
                                    "mountPath": "/tmp",
                                    "name": "console-web-tmp-volume",
                                },
                                {"name": "kubeconfig", "mountPath": "/opt/kubeconfig"},
                            ],
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": True,
                                "runAsUser": 1001,
                                "runAsGroup": 2001,
                                "capabilities": {"drop": ["ALL"]},
                            },
                            "resources": {
                                "requests": {"memory": "200Mi"},
                                "limits": {"memory": "400Mi"},
                            },
                        },
                    ],
                    "volumes": [
                        {
                            "name": "console-web-tmp-volume",
                            "emptyDir": {},
                        }
                    ],
                },
            )

    return template_patch
