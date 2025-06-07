.PHONY: run
run:
	uv run fastapi dev ./src/main.py

.PHONY: lint
lint:
	ruff format
	ruff check --fix

.PHONY: test
test:
	python3 -m pytest

.PHONY: deploy-gitlab
deploy-gitlab:
	ansible-playbook -i ./ansible/gitlab_inventory.ini ./ansible/gitlab_playbook.yml
