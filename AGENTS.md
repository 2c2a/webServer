<2c2a_iron_laws>
🚨 VIOLATION = SEVERE ERROR:
1. All Python cmds MUST use `uv run`. NO `pip`, NO bare `python`.
2. NO `django-admin` for provider/user dashboard. Build custom views.
3. NO raw `<style>`, NO inline styles. ONLY Tailwind atomic classes.
4. NO Bootstrap (`django-bootstrap5`).
5. Frontend (User) & Backend (Provider) styles MUST NOT mix.
6. ZERO CDN links. Download ALL assets to `static/vendor/` locally.
7. NO `SeparateDatabaseAndState` with empty `database_operations`.
8. Delete `feat/*` & `hotfix/*` branches IMMEDIATELY after merge.
</2c2a_iron_laws>

<rule_routing>
When working on a task, LOAD the matching rule file from rules/ directory:
- User-facing UI / front-end templates / MD3 styles          → rules/user-frontend.md
- Provider/Admin UI / backend dashboard / tech-monitor style  → rules/admin-backend.md
- Database migrations / makemigrations / migrate              → rules/migrations.md
- Git operations / branching / merging / PR                   → rules/git-workflow.md
- Debugging / env broken / port conflict / dependency issues  → rules/troubleshooting.md
If unsure, load the file. Better safe than sorry.
</rule_routing>
