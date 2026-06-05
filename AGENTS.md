# AGENTS.md

## Project context

Tianjun Engine is evolving from a research/demo dashboard into a modern enterprise-grade control console for compute-network resource scheduling.

The frontend is a React + Vite console. The backend is the Tianjun HTTP control plane. The UI must feel like a modern cloud console: clear hierarchy, high information density, safe operations, and explainable AI scheduling.

## Current frontend stack

- React + Vite
- Arco Design components
- ECharts for charts
- CSS modules are not used; styles are organized under `frontend/src/styles/`
- Theme is token-driven through CSS variables
- Backend calls must go through `frontend/src/services/api.js`
- Global control-plane data comes from `ControlPlaneProvider`
- Scheduling chat/session state must be preserved through `SchedulingSessionProvider`

## Important frontend directories

- `frontend/src/app/`  
  App entry, routes, top-level app composition.

- `frontend/src/layout/`  
  Console shell, sidebar, header, control-plane provider.

- `frontend/src/pages/`  
  Route-level pages.

- `frontend/src/features/`  
  Domain-level feature components.

- `frontend/src/features/scheduling/`  
  AI scheduling workbench, chat UI, policy workspace, tool trace, commit confirmation.

- `frontend/src/features/topology/`  
  Infrastructure topology components. The current active topology component is `InfrastructureTopology.jsx`.

- `frontend/src/styles/`  
  All console styles. Use the existing style split:
  - `tokens.css`
  - `layout.css`
  - `pages.css`
  - `overview.css`
  - `scheduling.css`
  - `workloads.css`
  - `infrastructure.css`
  - `model-policy.css`
  - `audit-settings.css`
  - `responsive.css`

## Architecture rules

- Do not reintroduce the old single-file dashboard architecture.
- Do not create or use `dashboardRuntime.js`.
- Do not use DOM-driven UI updates such as:
  - `document.getElementById`
  - `document.querySelector`
  - `innerHTML`
  - manual DOM event binding for React UI
- Use React state, props, hooks, and context.
- Route pages should be thin containers. Complex logic should live in feature components or hooks.
- Shared state that must survive route changes should live in a Provider, not inside a route component.
- Keep API calls in `frontend/src/services/api.js` or a dedicated service module under `frontend/src/services/`.

## Page structure

The console uses these primary pages:

- Overview
- Scheduling Workbench
- Workloads
- Infrastructure
- Model & Policy
- Audit & Settings

Use the route definitions in `frontend/src/app/routes.jsx`. Do not create duplicate routes or legacy dashboard pages.

## Layout rules

Use the page width classes consistently:

- `page-narrow` for reading/configuration-heavy pages
- `page-standard` for normal dashboard pages
- `page-wide` for workbench, table, and model/policy pages
- `page-full` for topology/infrastructure pages

Do not hard-code random page widths inside page-specific CSS. Prefer tokens from `tokens.css`:

- `--tj-page-narrow`
- `--tj-page-standard`
- `--tj-page-wide`
- `--tj-content-padding-x`
- `--tj-content-padding-y`
- `--tj-grid-gap`
- `--tj-grid-gap-lg`

If a new layout rule is needed across pages, add it to `tokens.css`, `pages.css`, or `responsive.css` rather than duplicating it.

## Theme rules

The console supports light and dark themes through CSS variables.

- Do not hard-code light-only colors like `#fff`, `#17243a`, `#dbe4f0` in new components.
- Use semantic tokens:
  - `--tj-bg`
  - `--tj-bg-page`
  - `--tj-surface`
  - `--tj-surface-solid`
  - `--tj-surface-muted`
  - `--tj-text`
  - `--tj-text-secondary`
  - `--tj-text-muted`
  - `--tj-line`
  - `--tj-line-soft`
  - `--tj-blue`
  - `--tj-green`
  - `--tj-purple`
  - `--tj-red`
  - `--tj-amber`
- If a feature needs new color semantics, add new tokens to `tokens.css` for both light and dark themes.
- Dark theme should be deep blue-black, not pure black.
- Charts and topology views must read theme tokens instead of using fixed colors.
- Topology-specific colors should use topology tokens such as:
  - `--tj-topology-bg`
  - `--tj-topology-line`
  - `--tj-topology-hub-bg`
  - `--tj-topology-zone-bg`
  - `--tj-topology-zone-shadow`

## AI scheduling workbench rules

The Scheduling Workbench is a core product surface.

- AI chat must be React state-driven.
- Tool calls should be shown as structured trace/timeline UI, not plain text.
- Do not show redundant text like “已完成” when icon/state already communicates completion.
- Do not show “正在生成...” as placeholder assistant content unless explicitly requested by product design.
- Empty states should be explicit, calm, and enterprise-style.
- The policy workspace must clearly show:
  - policy state
  - selected node
  - reason
  - latency
  - cost
  - risk
  - commit readiness

## Safety rules for scheduling and policy commit

Formal scheduling or policy commit must never happen from chat text alone.

Required behavior:

- The AI may draft a policy.
- The UI must show a policy workspace.
- The user must click a formal commit button.
- A confirmation dialog must appear.
- The request payload must include explicit confirmation, such as:
  - `confirmed_by_user_button: true`

Do not remove or bypass this safety boundary.

## State persistence rules

- Scheduling chat/session state must survive navigation between pages.
- Keep this state in `SchedulingSessionProvider`.
- Do not move scheduling session state back into `SchedulingPage` or `AICopilotPanel` if that causes route-switch data loss.
- If browser refresh persistence is implemented, prefer sessionStorage or backend session recovery with clear versioned keys.

## Infrastructure topology rules

The current active topology component is:

- `frontend/src/features/topology/InfrastructureTopology.jsx`

It supports region-level overview and drill-down into region nodes.

Do not accidentally use or revive legacy topology components unless explicitly requested. If keeping an experimental topology implementation, place it under an `experimental/` or `legacy/` folder and name it clearly.

Infrastructure page should generally use:

- left/topology view
- right/node table
- node detail drawer
- region filter/drill-down synchronization

## Table and enterprise UI rules

For enterprise console pages:

- Prefer tables, filters, drawers, tabs, and confirmation dialogs over large decorative cards.
- Tables should have stable `rowKey`.
- Avoid duplicate keys when combining pending/running/history rows.
- Every data-heavy page should support loading, empty, and error states.
- Empty states should not collapse card height.

## Style rules

- Avoid one-off CSS values when a token exists.
- Prefer semantic class names:
  - `tj-overview-*`
  - `tj-ai-*`
  - `tj-infra-*`
  - `tj-workload-*`
  - `tj-policy-*`
  - `tj-audit-*`
- Keep page-specific styles in their corresponding CSS file.
- Keep global layout rules in `layout.css`, `pages.css`, or `responsive.css`.
- Do not put large page-specific style blocks in `tokens.css`.

## Build and validation

Before considering a frontend change complete, run:

```bash
cd frontend
npm run build

If the change affects theme, verify both light and dark themes.

If the change affects scheduling, verify:

message sending
tool trace rendering
stop generation
policy workspace rendering
formal commit confirmation

If the change affects infrastructure, verify:

region overview
region drill-down
node table filtering
node detail drawer
light and dark topology appearance
Documentation maintenance

This file must be maintained.

Update AGENTS.md when any of the following changes:

frontend architecture
route structure
theme system
API service layout
scheduling safety rules
topology implementation
major component naming conventions
build/test commands
files that should be considered legacy or active

When in doubt, update this file in the same PR or commit as the code change.


---

## 我建议再加一句到 README

`README.md` 里可以加一个小节，不用太长：

```md
## AI agent development notes

This repository uses `AGENTS.md` to guide Codex and other AI coding agents. When changing frontend architecture, routing, theme tokens, scheduling safety rules, or topology implementations, update `AGENTS.md` together with the code.