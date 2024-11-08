(workshop-templates)=
Workshop Templates
==================

The Educates workshop template provides a starting point for creating your workshops. The template is tailored for working with the local Educates environment, but can be customized to suit any deployment of Educates. When creating a new workshop it is possible to provide options to customize the workshop details.

Customizing workshop details
----------------------------

To create a new workshop using the Educates command line tool you would run the `educates new-workshop` command, passing it as argument a directory path to where the workshop content should be placed.

```
educates new-workshop lab-new-workshop
```

The last component of the supplied path will be used as the workshop name. The name of the workshop must conform to what is valid for a RFC 1035 label name as detailed in [Kubernetes object name and ID](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/) requirements, but instead of a maximum length of 63 characters it is recommended the name be no longer than 25 characters. The shorter length requirement is due to Educates needing to add prefixes or suffixes as part of the implementation in different circumstances.

The ``educates new-workshop`` command will default to creating files setup for using the ``hugo`` renderer. If you want to use the older ``classic`` renderer use:

```
educates new-workshop lab-new-workshop --template classic
```

The `classic` renderer is deprecated and will in time be removed so it is recommended that new workshops use the `hugo` renderer.

In the workshop definition there are additional required fields that need to be filled out. These will be filled out with default values, but you can customize them at the time of workshop creation.

The command line options for customizing the fields and their purpose are:

* `--title` - A short title describing the workshop.
* `--description` - A longer description of the workshop.
* `--image` - The name of an alternate workshop base image to use for the workshop. Options for workshop base images supplied with Educates are `jdk8-environment:*`, `jdk11-environment:*`, `jdk17-environment:*`, `jdk21-environment:*` and `conda-environment:*`.

Custom workshop base image
--------------------------

The default workshop template uses an OCI image artifact to package up the workshop content files. This is overlayed on top of the standard base workshop image, or one of the alternatives provided with Educates. A typical configuration for this which would be found in the `resources/workshop.yaml` file would be:

```yaml
spec:
  workshop:
    files:
    - image:
        url: $(image_repository)/{name}-files:$(workshop_version)
      includePaths:
      - /workshop/**
      - /exercises/**
      - /README.md
```

In the example above, the value of `{name}` would be the name of your workshop. That is, the same as `metadata.name` from the same resource definition.

In the value for `files.image.url`, the reference to the data variable `$(image_repository)` will ensure that the OCI image artifact containing the workshop content files are pulled from the image registry created with the local Kubernetes environment. That is, you do not need to provide an explicit name for the image registry host as Educates will substitute the appropriate value. The data variable `$(workshop_version)` will be substituted with `latest` when working on content. Both of these will be replaced with actual values when a workshop is published.

If you want to use your own custom workshop image, the location of the image can be supplied using the `--image` option when using the `educates new-workshop` command to create the initial workshop content. This would result in the generated configuration found in `resources/workshop.yaml` including the extra `spec.workshop.image` property.

```yaml
spec:
  workshop:
    image: custom-environment:latest
    files:
    - image:
        url: $(image_repository)/{name}-files:$(workshop_version)
      includePaths:
      - /workshop/**
      - /exercises/**
      - /README.md
```

If the custom workshop image is specific to the workshop and is not being built and published separately, you can add a `Dockerfile` for creating the custom workshop image to the workshop files. To also use the local image registry for it, you would then set the `spec.workshop.image` property as follows:

```yaml
spec:
  workshop:
    image: $(image_repository)/{name}-image:$(workshop_version)
    files:
    - image:
        url: $(image_repository)/{name}-files:$(workshop_version)
      includePaths:
      - /workshop/**
      - /exercises/**
      - /README.md
```

To build the custom workshop base image and push it to the local registry you would run:

```
docker build -t localhost:5001/{name}-image:latest .
```

The custom workshop base image would then be pulled down from the local image registry for each workshop session.

Note that although it is possible to create custom workshop images, it is recommended that it be avoided if possible. If you need to add additional applications to a workshop session use extension packages instead. By overlaying additional files onto one of the standard workshop base images at the time a workshop is created, rather than creating a custom workshop image, you ensure you are always using the appropriate version of the workshop base image for the version of Educates being used. Using a custom workshop image that is based on an older version of the workshop base images is not guaranteed to always work.

Hosting workshops on GitHub
---------------------------

If hosting workshops on GitHub, the Educates project provides a GitHub action to assist in automatically publishing tagged versions of workshops as releases to GitHub. To make use of the GitHub action, add to your Git repository the file `.github/workflows/publish-workshop.yaml` containing:

```
name: Publish Workshop

on:
  push:
    tags:
      - "[0-9]+.[0-9]+"
      - "[0-9]+.[0-9]+-alpha.[0-9]+"
      - "[0-9]+.[0-9]+-beta.[0-9]+"
      - "[0-9]+.[0-9]+-rc.[0-9]+"

jobs:
  publish-workshop:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Create release
        uses: educates/educates-github-actions/publish-workshop@v6
        with:
          token: ${{secrets.GITHUB_TOKEN}}
```

With the GitHub workflow added, when you are ready to make your workshop available for others to use, use `git` to create a version tag against the commit for the stable version, where the format of the tag is `X.Y`, e.g., `1.0`. Push the tag to GitHub.

The tag being pushed to GitHub will trigger the following actions:

* Creation of an OCI image artefact containing workshop content files and pushing it to the GitHub container registry.
* Creation of a release against the GitHub repository and attach as assets Kubernetes resource files for deploying the workshop to Educates.

The creation and the publishing of the OCI image artefact will be performed using the `educates publish-workshop` command. Your workshop definition must therefore be configured appropriately with a section describing how to publish the workshop image and optionally what should be included in the workshop image. In the case of workshops created using the `educates new-workshop` command, this configuration will be:

```yaml
spec:
  publish:
    image: $(image_repository)/{name}-files:$(workshop_version)
```

In the example above, the value of `{name}` would be the name of your workshop. That is, the same as `metadata.name` from the same resource definition. The image reference will match what is used in `spec.workshop.files.image.url`.

Note that if the GitHub repository is not public, you will need to go to the settings for any images pushed to GitHub container registry and change the visibility from private or internal, to public before anyone can use the workshop.

To use the workshop, you can explicitly load the workshop definition using the `workshop.yaml` file attached to the GitHub release, and then add it to an appropriate training portal, or you could use the Educates command line and run `educates deploy-workshop` supplying the URL for the `workshop.yaml` file attached to the GitHub release: 

```
educates deploy-workshop -f https://github.com/educates/lab-k8s-fundamentals/releases/latest/download/workshop.yaml
```

See the more detailed [documentation](https://github.com/educates/educates-github-actions/blob/main/publish-workshop/README.md) about the GitHub action used to publish the workshop on how to configure it.
