# Tianjun Console UI Agent Instructions

## Goal
Build a modern enterprise control console for Tianjun Engine.

## Frontend rules
- Use React state, props, and hooks.
- Do not use document.getElementById, querySelector, or innerHTML for UI updates.
- All backend calls must go through frontend/src/api/.
- Components must support loading, error, and empty states.
- Prefer enterprise dashboard patterns: AppShell, sidebar navigation, page header, metric cards, data tables, drawers, tabs, confirmation dialogs.

## UI library
- Use Arco Design or Ant Design components.
- Use ECharts for charts.
- Use AntV G6 for topology graphs.

## Pages
- OverviewPage
- SchedulingPage
- WorkloadsPage
- InfrastructurePage
- ModelPolicyPage
- AuditSettingsPage

## Domain components
- TaskTable
- NodeTable
- PolicyLifecycle
- PolicyWeightRadar
- ModelRuntimeCard
- TopologyGraph
- ExecutionTimeline
- StatusBadge
- ConfirmCommitDialog

## Safety
- Policy commit and task scheduling must require explicit button confirmation.
- Never trigger commit from chat text alone.