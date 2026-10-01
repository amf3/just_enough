# My Things TO DO List

* standardize POSIX user and group entries across all images.
     * busybox is built first and will contain passwd & group entries
     * busybox image is used with mulltistage build for  python, unbound_dns, and samba images
     * During build, /etc/passwd, /etc/group, /etc/nsswith is copied into python, unbound, and samba image.
     * Unbound Dockerfile will need to append unbound user and group entries

* Documentation additions
     * Add container image documentation by creating a README.md in each project_manifest/{container} directory
     * Readme's should state why container was created, along with how and where to use it.
     * Add a landing page (README.md) in the docs dir linking to the manifest definition and each container readme

