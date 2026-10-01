# The JustEnough Samba Container Image

This image will let one deploy a [Samba](https://www.samba.org) server as a container.  It does require some setup before deployment.

Start by copying the [samba4](https://github.com/amf3/just_enough/tree/main/project_manifest/samba4) directory locally with either git or wget to a working directory.

## Samba Project Files

**container_def.yml** : This defines what files get copied from the buildroot environment into the container image.  Used during the base image build and safe to ignore.

**docker-compose.yml** : Use this file for deploying the container image. It contains an inline Dockerfile that builds from the public base samba image and lets one modify user credentials and storage locations. 

**Dockerfile** : This is the Dockerfile used to create the public samba image. It includes a `healthcheck` user with hard coded credentials.  See below on how to change it's credentials.

**group** and **passwd** : Standard POSIX files to define accounts for `root` and `nobody`.  Used during the base image build and safe to ignore.

**samba_groups** and **samba_secrets** : Plain text user credentials for the smbd service. Both are used to define local user accounts and multi-member groups inside the container.

**smb.conf** : This is the configuration file for smbd. It contains a base do-nothing config and commented examples for creating a standard data share and a time machine share.

## How do I use this image?

The base samba image is intended to be modified by local admins before deployment.  

### User credentials 

Start by adding user credentials to samba_secrets and update the password for healthcheck.  The format for samba_secrets is described in the file header. Each line is a record and contains the UID, the account name, and the plaintext password, `1000:healthcheck:AMIOK`. Start with a UID of 1001 and keep incrementing by one for each new account.

If there are any shared groups, add the list of users to samba_secrets.  The format is each line is a record containing the groupname, GID, and comma seperated list of group members, `data_share_group:2000:bob,alice`.  Because each UID gets its own unique GID, (UID 1000 has a matching GID 1000), it's recomended to start incrementing shared GIDs from 2000 so GIDs don't collide.

### docker-compose.yml and smb.conf changes

Next uncomment the HEALTHCHECK line in the docker-compose.yml file and update the healthcheck password if it's been modified.  One should also modify the VOLUMEs inside docker-compose. 

Update smb.conf and uncomment the data share and timemachine share blocks so smbd will present a network share.

### Apply the modifications to the base image

Using `docker-compose build` will apply local changes to the public samba image and create a samba-appliance:local image.  Running `docker compose up` will then launch the image.

### Saving modifications

Because samba_secrets contain plaintext passwords, it's recommended to store the file contents inside a software vault like the [1Password API](https://www.1password.dev/get-started/developer-quickstart).

Changes to the docker-compose.yml, smb.conf, and samba_groups files can be stored in a local git repo.