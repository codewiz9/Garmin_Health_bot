---
name: django-view-link-checker
description: Verify that Django views are correctly wired through URL patterns and reachable from the main HTML entry page navigation. Use when working on Django views, urls.py files, templates, route wiring, page linking, or when the user asks to confirm view-to-URL-to-template integration.
---

# Django View Link Checker

## Purpose

Ensure each user-facing Django view is:

1. Registered in the correct `urls.py` file.
2. Exposed through project URL includes as needed.
3. Reachable from the main HTML page (or shared layout navigation).

## Workflow

Use this checklist and report pass/fail for each item:

```text
View Wiring Checklist
- [ ] View exists and is intended to be user-facing
- [ ] URL pattern exists for the view
- [ ] URL name is defined and consistent
- [ ] Parent project urls.py includes the app URLs if required
- [ ] Main HTML page (or base layout) links to the named URL
- [ ] Link target resolves to the expected route and template
```

## Step 1: Identify View Scope

- Collect Django views from `views.py` and class-based views in app modules.
- Exclude internal/API-only views unless the user requests them.
- Treat only user-facing pages as required navigation targets.

## Step 2: Validate URL Mapping

For each user-facing view:

- Confirm a `path()` or `re_path()` exists in app `urls.py`.
- Prefer `name=` for every route; flag missing names.
- Confirm the project-level `urls.py` includes app URLs (`include(...)`) where needed.
- Flag mismatched imports, wrong view references, duplicate names, and dead routes.

## Step 3: Validate Main Page Linking

- Determine main entry template in this order:
  1. Explicit user-specified page
  2. `templates/base.html`
  3. `templates/index.html`
  4. App-level template that serves as global navigation
- Check for links using `{% url 'name' %}` and compare against route names.
- If hardcoded paths are used, verify they match actual resolved routes.
- Flag views that are routable but not linked from the main page/navigation.

## Step 4: Report Findings

Output concise findings grouped by severity:

- Critical: view not routed, broken include chain, broken template link.
- Warning: routable view not linked from main page/nav.
- Suggestion: hardcoded links should use `{% url %}` and named routes.

For each issue, include:

- View symbol (or class)
- Expected URL name/path
- Actual mismatch
- Exact file path to fix
- Minimal recommended fix

## Preferred Fix Patterns

- Add missing `name=` to URL routes.
- Use namespaced URLs where apps expose overlapping names.
- Replace hardcoded href paths with `{% url 'app_name:view_name' %}`.
- Keep main navigation in one shared template to avoid drift.

## Notes

- If no single "main HTML page" exists, treat the shared base layout and primary navbar as the main entry surface.
- Ask for clarification only when multiple independent entry points exist and none is canonical.
