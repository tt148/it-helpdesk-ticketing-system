# HelpDesk Pro

**A role-based IT helpdesk platform for ticket lifecycle management, SLA tracking, knowledge sharing, and support analytics.**

HelpDesk Pro demonstrates how an internal IT support team can record incidents, route requests to technicians, communicate safely with employees, track service targets, and turn repeat fixes into reusable knowledge.

## Why this matters

Support requests scattered across email and chat are hard to prioritize, audit, or measure. HelpDesk Pro centralizes ticket ownership and status, keeps technician-only notes private, flags SLA risk, and provides an auditable record of work.

## Features

- Role-aware access: Employee, Technician, and Admin.
- Ticket creation, assignment, filtering, search, status lifecycle, and audit history.
- Public replies and internal technician notes.
- Priority-based SLA targets: Critical 4h, High 8h, Medium 48h, Low 72h.
- Dashboard metrics, category/technician counts, and CSV report export.
- Searchable knowledge base and article creation from resolved tickets.
- DRF ticket/comment endpoints, token/session authentication, Swagger UI and ReDoc.
- Email notifications for assignment, status changes, and comments; console backend by default.
- SQLite for quick local development and PostgreSQL for Docker/production.
- Docker Compose, GitHub Actions CI, pytest, and Ruff.

## Stack

Python 3.12 · Django 5.x · Django REST Framework · PostgreSQL · SQLite · Bootstrap 5 · drf-spectacular · Docker · pytest · Ruff · GitHub Actions.

## Architecture and data model

- `accounts`: custom user model, roles, and admin-only user management.
- `tickets`: categories, tickets, comments, audit events, SLA rules, web views, API serializers and permissions.
- `kb`: searchable articles with optional source-ticket references.
- `dashboard`: role-scoped aggregate metrics.
- `config`: settings, root routes, API schema, WSGI/ASGI, and error handlers.

Core relationships: each ticket has a requester and optional assignee, belongs to a category, and has many comments and audit records. A knowledge article may be linked to a resolved source ticket.


## Run locally (SQLite)

Requirements: Python 3.11+ and pip.

```bash
git clone <your-repository-url>
cd helpdesk-pro
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Open http://127.0.0.1:8000. The `.env.example` defaults to SQLite and console email. Replace the development secret before any public deployment.

## Run with Docker (PostgreSQL)

```bash
cp .env.example .env
# Set DJANGO_SECRET_KEY in .env to a unique random secret
docker compose up --build
```

Open http://localhost:8000. In another terminal, seed demo data:

```bash
docker compose exec web python manage.py seed_demo
```

Stop with `docker compose down`; retain database data with the named volume. `docker compose down -v` deletes the local database volume.

## Tests and quality checks

```bash
python manage.py check
python manage.py migrate
ruff check .
pytest
```

Tests cover API visibility, cross-user isolation, internal-note privacy, status transition validation, SLA deadline/overdue behavior, and token auth.

## API documentation

- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`
- OpenAPI schema: `/api/schema/`
- Token endpoint: `POST /api/token/` with `username` (email) and `password`.
- Ticket collection: `/api/tickets/`; ticket comments: `/api/tickets/{id}/comments/`.

Use `Authorization: Token <token>` for token-authenticated API calls. Session authentication is also enabled for browser/API clients. Employees are scoped to their own tickets and public comments; technicians/admins can see all tickets.

## Demo credentials

All seeded accounts use the development-only password `DemoPass123!`.

| Role | Email |
|---|---|
| Admin | `admin@demo.com` |
| Technician | `tech@demo.com` |
| Technician | `tech2@demo.com` |
| Employee | `employee@demo.com` |
| Employee | `employee2@demo.com` |
| Employee | `employee3@demo.com` |

**Do not use demo credentials on a public deployment.** Disable or change seeded accounts before sharing a live instance.

## Deploy to Render

1. Push the repository to GitHub.
2. Create a Render Blueprint from the repository; `render.yaml` declares the web service and PostgreSQL database.
3. Verify `DJANGO_ALLOWED_HOSTS` matches the actual Render hostname. Keep `DJANGO_DEBUG=False` and use a generated secret.
4. For production email, configure an SMTP provider and set `EMAIL_BACKEND`, credentials, and sender address through Render environment variables.
5. After deploy, run `python manage.py seed_demo` only if you deliberately want demo data; rotate/remove demo accounts before public access.
6. Add the live URL and screenshots to this README.

For a production deployment, use a paid managed database with backups, configure HTTPS/proxy security settings, rate limiting, monitoring, and a real email provider. Review database connection SSL settings for your provider.

## Roadmap

- Dedicated response and resolution SLA clocks, business-hours calendars, and escalation policies.
- Notifications via a real transactional email provider and user notification preferences.
- Attachments, ticket watchers, canned responses, and richer technician workload assignment.
- Pagination/filter UI refinements and richer chart visualizations.
- Stronger audit immutability, structured logging, security headers, and coverage reporting.
- Add Playwright end-to-end tests and accessibility checks.

## Why I built this

I wanted a portfolio project that connects practical IT support work—triage, account access, hardware/network incidents, user communication, and documentation—with the software engineering practices behind a maintainable service: clear models, API permissions, tests, containerization, CI, and deployment documentation.

## License

MIT. See [LICENSE](LICENSE).
