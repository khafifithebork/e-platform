import { afterEach, describe, expect, it, vi } from "vitest";

import { createSessionStatusStore } from "./session-status";

afterEach(() => vi.unstubAllGlobals());

describe("browser session observations", () => {
  it("does not call an anonymous visit an ended session", () => {
    const store = createSessionStatusStore();
    store.authenticationRequired(store.begin(), "Authentication required.");
    expect(store.getSnapshot()).toEqual({ status: "unknown" });
  });

  it("records a refusal only after confirmation and preserves the server detail", () => {
    const store = createSessionStatusStore();
    store.confirm(store.begin());
    expect(store.getSnapshot()).toEqual({ status: "confirmed" });
    store.authenticationRequired(store.begin(), "The server's exact message.");
    expect(store.getSnapshot()).toEqual({ status: "ended", detail: "The server's exact message." });
  });

  it("notifies once for concurrent refusals and supports unsubscribe", () => {
    const store = createSessionStatusStore();
    store.confirm(store.begin());
    const first = store.begin();
    const second = store.begin();
    const notify = vi.fn();
    const unsubscribe = store.subscribe(notify);
    store.authenticationRequired(first, "Signed out.");
    store.authenticationRequired(second, "Another response.");
    expect(notify).toHaveBeenCalledTimes(1);
    unsubscribe();
    store.confirm(store.begin());
    expect(notify).toHaveBeenCalledTimes(1);
  });

  it("does not use a request begun anonymously to invalidate later confirmation", () => {
    const store = createSessionStatusStore();
    const anonymous = store.begin();
    store.confirm(store.begin());
    store.authenticationRequired(anonymous, "Old anonymous response.");
    expect(store.getSnapshot().status).toBe("confirmed");
  });

  it("does not let an old confirmation undo a newer session loss", () => {
    const store = createSessionStatusStore();
    store.confirm(store.begin());
    const oldMe = store.begin();
    store.authenticationRequired(store.begin(), "Signed out.");
    store.confirm(oldMe);
    expect(store.getSnapshot().status).toBe("ended");
    store.confirm(store.begin());
    expect(store.getSnapshot().status).toBe("confirmed");
  });

  it("ignores older refusals when a newer request confirms the session", () => {
    const store = createSessionStatusStore();
    store.confirm(store.begin());
    const oldRefusal = store.begin();
    store.confirm(store.begin());
    store.authenticationRequired(oldRefusal, "Stale refusal.");
    expect(store.getSnapshot().status).toBe("confirmed");
  });

  it.each(["login", "logout"] as const)("excludes intentional %s and its in-flight observations", (intent) => {
    const store = createSessionStatusStore();
    store.confirm(store.begin());
    const oldRequest = store.begin();
    const operation = store.begin(intent);
    store.authenticationRequired(oldRequest, "Old refusal.");
    const duringOperation = store.begin();
    store.confirm(duringOperation);
    store.authenticationRequired(operation, "Operation refusal.");
    expect(store.getSnapshot().status).toBe("unknown");
    store.finish(operation);
    store.confirm(duringOperation);
    expect(store.getSnapshot().status).toBe("unknown");
    store.confirm(store.begin());
    expect(store.getSnapshot().status).toBe("confirmed");
  });

  it("keeps its server snapshot neutral and never stores identity or credentials", () => {
    const store = createSessionStatusStore();
    store.confirm(store.begin());
    expect(store.getServerSnapshot()).toEqual({ status: "unknown" });
    const localWrites = vi.spyOn(Storage.prototype, "setItem");
    store.authenticationRequired(store.begin(), "Signed out.");
    expect(localWrites).not.toHaveBeenCalled();
    localWrites.mockRestore();
    expect(Object.keys(store.getSnapshot())).toEqual(["status", "detail"]);
  });

  it("does not mutate or subscribe in a server environment", () => {
    vi.stubGlobal("window", undefined);
    const store = createSessionStatusStore();
    const notify = vi.fn();
    store.subscribe(notify);
    store.confirm(store.begin());
    store.authenticationRequired(store.begin(), "Never stored.");
    expect(store.getSnapshot()).toEqual({ status: "unknown" });
    expect(notify).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
    expect(store.getSnapshot()).toEqual({ status: "unknown" });
  });
});
