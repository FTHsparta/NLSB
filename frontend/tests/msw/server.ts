import { setupServer } from "msw/node";

/**
 * No default handlers -- every integration test registers exactly the
 * `/translate`/`/correct`/`/confirm` responses it needs via `server.use(...)`.
 * An unhandled request is a test bug (a route the test forgot to stub),
 * not something to paper over with a fallback handler.
 */
export const server = setupServer();
