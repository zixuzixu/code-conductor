# Phase 6: Frontend MVP Design

## Goal
React frontend for Code Conductor — three-panel Linear-style UI with Sessions sidebar, Chat panel (SSE streaming), and Threads task panel.

## Tech Stack
- Vite + TypeScript + React
- Tailwind CSS + shadcn/ui (dark theme)
- pnpm

## Layout
Three columns: Sessions (240px) | Chat (flex-1) | Threads (320px)

## Structure
```
web/
├── index.html, package.json, vite.config.ts, tailwind.config.ts
├── components.json (shadcn/ui)
└── src/
    ├── main.tsx, App.tsx, globals.css
    ├── lib/api.ts, lib/utils.ts
    ├── hooks/use-sessions.ts, use-chat.ts, use-tasks.ts, use-websocket.ts
    └── components/{sidebar,chat,threads}/
```

## API Integration
- Sessions: REST CRUD via `/api/sessions`
- Chat: SSE POST `/api/chat` with ReadableStream parsing
- Tasks: REST CRUD via `/api/threads/tasks`
- WebSocket: `/ws/sessions/{id}` for real-time worker events

## Key Decisions
- No state management library (useState + props)
- No React Query (custom fetch hooks)
- SSE via fetch + ReadableStream (EventSource doesn't support POST body)
- shadcn/ui components: Button, Input, Card, Badge, ScrollArea
- Dark theme default
- No routing (single page, session switching via state)

## Out of Scope
PWA, Voice, Plan review UI, responsive mobile, Memory editor UI
