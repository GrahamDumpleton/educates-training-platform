Version 3.2.2
=============

Bugs Fixed
----------

* Embedded VS Code was not working when workshop was accessed via insecure HTTP
  connection. Upgraded VS Code version to fix issue.

* Ingresses, including those for embedded applications such as the editor, were
  not working when deploying a workshop to local docker environment.
