# 0006: Server-Sent Events, not WebSockets, for the dashboard

**Status:** accepted (stage 6)

## Options

1. **Server-Sent Events** (`GET /api/stream`, `text/event-stream`).
2. **WebSockets** (STOMP over Spring's WebSocket support).
3. **Polling** every few seconds.

## Decision

Option 1.

## Why

- The data flows one way: server to browser. The dashboard never pushes anything that needs a
  persistent connection (acknowledging an alert is one POST).
- SSE is plain HTTP: it works through every proxy and load balancer that handles long responses,
  needs no upgrade handshake, and `EventSource` reconnects by itself with `Last-Event-ID`.
- Named events (`status`, `alert`, `score`) map directly onto `addEventListener` in the browser,
  and the payloads are small JSON objects.
- One `SseEmitter` per client, a `CopyOnWriteArrayList` of them, and Spring's event bus: about
  60 lines of code and nothing to configure.

## What we gave up

- Binary frames and bidirectional traffic (not needed).
- Browsers cap SSE connections per origin on HTTP/1.1 (six); fine for a dashboard, and HTTP/2
  removes the cap.
- A very busy stream (200 score events per second during a replay) is a lot of small messages.
  The dashboard tolerates it by redrawing the fleet table on a timer instead of per event; a
  production version would sample or batch `score` events server-side per machine.

## When WebSockets would win

Collaborative editing, chat, anything where the browser sends a stream, or a need for a single
multiplexed connection with many subscriptions managed by the server (STOMP destinations).
