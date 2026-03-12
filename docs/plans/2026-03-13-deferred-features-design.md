# Deferred Features Design — Code Conductor

## Overview

Six deferred features from Phase 7 to be implemented in order of complexity.

## 1. Responsive Design

**Goal:** Three-panel layout adapts to mobile/tablet/desktop.

**Breakpoints (Tailwind):**
- `<768px` (mobile): Single column, bottom tab navigation
- `768-1024px` (tablet): Two columns (sidebar collapses)
- `>1024px` (desktop): Current three-column layout

**Approach:**
- App.tsx: Add `activePanel` state for mobile navigation
- Mobile: Bottom tab bar (Sessions / Chat / Tasks) — show one panel at a time
- Tablet: Hide sidebar, toggle with hamburger; Chat + Threads visible
- Desktop: Unchanged current layout
- All panels get responsive width classes (`w-full lg:w-60`, etc.)

**Components affected:** App.tsx, session-list.tsx, chat-panel.tsx, thread-panel.tsx

## 2. PWA Support

**Goal:** Installable web app with offline shell caching.

**Components:**
- `web/public/manifest.json` — app metadata, icons, standalone display
- `web/src/sw.ts` — Workbox-based service worker (cache shell, network-first API)
- `web/src/main.tsx` — SW registration
- SVG icon generation (simple conductor icon)

**Caching strategy:**
- Shell resources (HTML, CSS, JS): Cache-first
- API calls: Network-only (no offline API)
- WebSocket: Not cached

## 3. Voice API + Push-to-Talk

**Backend (`/api/voice`):**
- `POST /api/voice` accepts `multipart/form-data` with audio file
- Uses Gemini API for audio transcription (gemini-2.0-flash or similar)
- Returns `{ text: string, disclaimer: string }`
- New file: `src/conductor/api/voice.py`

**Frontend:**
- `web/src/components/chat/voice-button.tsx` — mic button next to chat input
- `web/src/hooks/use-voice-recorder.ts` — MediaRecorder API hook
- Recording states: idle → recording → transcribing → done
- Visual feedback: pulsing mic icon, timer display

## 4. Plan Mode API + Checklist UI

**Backend:**
- Pydantic models: `PlanStep`, `Plan` in models.py
- `src/conductor/api/plans.py` — CRUD endpoints:
  - `POST /api/plans` — create plan from task description
  - `GET /api/plans/{plan_id}` — get plan with steps
  - `PATCH /api/plans/{plan_id}` — edit steps, approve/reject
  - `POST /api/plans/{plan_id}/execute` — convert approved steps to tasks
- `src/conductor/managers/plan_manager.py` — plan lifecycle management
- Plans stored as JSON files in session directory

**Frontend:**
- `web/src/components/plans/plan-checklist.tsx` — step list with checkboxes
- `web/src/components/plans/plan-step.tsx` — individual step editor
- `web/src/hooks/use-plans.ts` — plan state management
- Integration with chat panel (plan displayed inline or as modal)

## Implementation Order

1. Responsive Design (CSS only, no new files)
2. PWA (manifest + SW, minimal backend)
3. Voice (new API endpoint + frontend component)
4. Plan Mode (new API + manager + frontend components)
