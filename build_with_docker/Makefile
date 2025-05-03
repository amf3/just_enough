ENV_FILE := .env

.PHONY: prepare_env prepare_container prepare build launch clean

# Generate .env file only if it doesn't exist
prepare_env:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "Generating $(ENV_FILE)..."; \
		echo "MY_UID=$$(id -u || echo 1000)" > $(ENV_FILE); \
		echo "MY_GID=$$(id -g || echo 1000)" >> $(ENV_FILE); \
	else \
		echo "$(ENV_FILE) already exists. Skipping..."; \
	fi

prepare_container:
	docker compose build --pull

# prepare both env and container, env is optional now
prepare: prepare_env prepare_container

# build target does NOT force prepare_env anymore
build:
	docker compose build

launch: prepare
	docker compose run builder bash

clean:
	rm -f .env
	docker compose down --volumes --remove-orphans

