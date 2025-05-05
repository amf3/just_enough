
.PHONY: create start stop shell clean copy_to copy_configs get_rootfs

create:
	# install software via cloud-init
	multipass launch -n just-enough --cloud-init just_enough_init.yml -c 8 -m 8G -d 32G -v lts

start:
	multipass start just-enough

stop:
	multipass stop just-enough

shell:
	multipass shell just-enough

clean:
	multipass delete just-enough
	multipass purge

copy_to:
	multipass transfer -r .. just-enough:/home/ubuntu/just_enough

get_configs:
	multipass transfer -r just-enough:/home/ubuntu/just_enough/configs ..

get_rootfs:
	multipass transfer -r just-enough:/home/ubuntu/just_enough/images/rootfs.tar.gz  .
