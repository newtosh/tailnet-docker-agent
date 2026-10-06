.PHONY: render test up down logs

render:
	python3 render/render.py

test:
	python3 -m unittest discover -s tests -v

up: render
	docker compose -f generated/docker-compose.yml --env-file .env up -d --build

down:
	docker compose -f generated/docker-compose.yml --env-file .env down

logs:
	docker compose -f generated/docker-compose.yml logs -f stack-agent
