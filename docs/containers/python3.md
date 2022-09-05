# Python Container Image

## About

This container contains Python3 only. Because it doesn't have /bin/sh, it can only be used as part of multi-stage build.  See [bash_python3.md](../bash_python.md) for more details & usage examples.  

The container size with python3 only is ~35Megabytes in size.
## Container contents
* The C library is glibc 2.35.134
* Python 3.10.5
* Pip 21.2.4
* Setuptools 62.1.0
* There is **no shell** with this container.
* An application user named **appuser** is included with the container image.
