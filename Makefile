.PHONY: help build up down logs clean prod-up prod-down prod-logs

# Default help target
help:
	@echo "Available commands:"
	@echo "  make build      - Build development images"
	@echo "  make up         - Start development environment"
	@echo "  make down       - Stop development environment"
	@echo "  make logs       - Show development logs"
	@echo "  make clean      - Remove containers and volumes"
	@echo "  make prod-up    - Start production environment"
	@echo "  make prod-down  - Stop production environment"
	@echo "  make prod-logs  - Show production logs"

# Development commands
build:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml build

up:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml up -d

down:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml down

logs:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml logs -f

clean:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml down -v
	docker system prune -f

# Production commands
prod-build:
	docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml build
	
prod-up:
	docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml up -d

prod-down:
	docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml down

prod-logs:
	docker-compose -f docker-compose.base.yml -f docker-compose.prod.yml logs -f

# Database operations
db-shell:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml exec db psql -U ${DB_USER} -d ${DB_NAME}

# Utility commands
migrate:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml exec costmetrix python manage.py migrate

collectstatic:
	docker-compose -f docker-compose.base.yml -f docker-compose.override.yml exec costmetrix python manage.py collectstatic --noinput