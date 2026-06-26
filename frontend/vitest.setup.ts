import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./tests/msw/server";

// Mocks the fetch boundary for integration tests (`TranslateFlow` rendered
// with its real default `httpTranslationApi`, no fake `api` prop) -- the
// component-level contract tests still inject a fake `api` directly and
// never touch the network, so this has no effect on them.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
