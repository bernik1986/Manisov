const { test, expect } = require("@playwright/test");
const path = require("node:path");

const ORIGIN = "http://127.0.0.1:15486";
const DIST = path.resolve(__dirname, "../../../generated/auth-session-20261120/dist");
const userA = { user_id: 9001, username: "synthetic-alpha", role: "recruiter" };
const userB = { user_id: 9002, username: "synthetic-beta", role: "viewer" };
const token = (claims = {}, seconds = 3600) => `test.${Buffer.from(JSON.stringify({
  sub: "9001", sid: "session-alpha", ver: "version-alpha",
  exp: Math.floor(Date.now() / 1000) + seconds, ...claims,
})).toString("base64url")}.test`;
const tokenB = (seconds = 3600) => token({ sub: "9002", sid: "session-beta", ver: "version-beta" }, seconds);
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1QAAAAASUVORK5CYII=", "base64");
const entry = page => page.locator(".candidate-document-intake > button").first();
const correction = page => page.locator("dialog.intake-dialog .intake-fields input[type=text]").first();

test.beforeEach(async ({ context }) => {
  await context.route("**/*", route => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort();
    const p = url.pathname;
    if (p === "/api/candidates/900001") return route.fulfill({ json: {
      candidate: { candidate_id: 900001, surname: "SYNTHETIC", first_name: "ALPHA", email: "synthetic@example.invalid" },
    } });
    if (p.endsWith("/document-intake/status")) return route.fulfill({ json: { enabled: true } });
    if (p.endsWith("/document-intake/submissions")) return route.fulfill({ json: { items: [], upload_enabled: true } });
    if (p.includes("/files/")) return route.fulfill({ contentType: "image/png", body: PNG });
    if (p.endsWith("/document-intake")) return route.fulfill({ json: {
      candidate_name: "SYNTHETIC ALPHA", existing: [],
      catalog: [{ key: "document:SB", kind: "document", label: "Book", fields: ["number"] }],
      batches: [{ batch_id: "synthetic-batch", created_at: new Date().toISOString(), items: [{
        file_id: "synthetic-file", name: "synthetic.png", content_type: "image/png",
        type_key: "document:SB", fields: { number: "BASELINE" }, saved: false, warnings: [],
      }] }],
    } });
    if (p.startsWith("/api/")) return route.fulfill({ json: { items: [], companies: [], vessels: [] } });
    if (p === "/auth-test") return route.fulfill({ contentType: "text/html", body:
      '<!doctype html><html><body><div id="root"></div><script type="module" src="/auth-session-harness.js"></script></body></html>',
    });
    if (p.startsWith("/assets/") || /^\/auth-session-[a-z]+\.js$/.test(p)) {
      return route.fulfill({ path: path.join(DIST, p.slice(1)) });
    }
    return route.fulfill({ path: path.join(DIST, "index.html") });
  });
});

async function boot(page, { jwt = token(), user = userA, app = false } = {}) {
  await page.addInitScript(({ jwt, user }) => {
    if (!localStorage.getItem("authTestSeeded")) {
      localStorage.setItem("authTestSeeded", "1");
      if (jwt) localStorage.setItem("authToken", jwt);
      if (user) localStorage.setItem("authUser", JSON.stringify(user));
    }
  }, { jwt, user });
  await page.goto(app ? "/candidates/900001" : "/auth-test");
  if (app) await expect(page.getByTestId("candidate-detail")).toBeVisible();
  else await expect.poll(() => page.evaluate(() => Boolean(window.authTest?.auth))).toBe(true);
}

async function hold(page, endpoint) {
  const state = { requests: [], release: null };
  await page.route(`**/api/${endpoint}`, async route => {
    state.requests.push(route.request());
    await new Promise(resolve => {
      state.release = async (json, status = 200) => {
        await route.fulfill({ status, json }).catch(() => {});
        resolve();
      };
    });
  });
  return state;
}

async function started(held) {
  await expect.poll(() => Boolean(held.release)).toBe(true);
}

async function start(page, name = "pending", endpoint = "/synthetic-private") {
  await page.evaluate(({ name, endpoint }) => window.authTest.start(name, endpoint), { name, endpoint });
}

async function result(page, name = "pending", ok = false) {
  await expect.poll(() => page.evaluate(name => window.authTest.results[name]?.ok, name)).toBe(ok);
  return page.evaluate(name => window.authTest.results[name], name);
}

async function mockLogin(page, jwt = tokenB(), user = userB) {
  await page.route("**/api/auth/login", route => {
    expect(route.request().headers().authorization).toBeUndefined();
    return route.fulfill({ json: { access_token: jwt, user } });
  });
}

async function login(page) {
  await page.evaluate(() => window.authTest.auth.login("synthetic", "synthetic-password"));
}

test("held refresh cannot restore credentials or dispatch private work after logout", async ({ page }) => {
  const held = await hold(page, "auth/refresh");
  let privateRequests = 0;
  await page.route("**/api/synthetic-private", route => { privateRequests++; return route.fulfill({ json: {} }); });
  await boot(page, { jwt: token({}, 60) });
  await start(page);
  await started(held);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
  expect((await result(page)).code).toBe("ERR_CANCELED");
  await held.release({ access_token: token({}, 7200), user: userA });
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
  expect(privateRequests).toBe(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
});

for (const status of [200, 401]) {
  test(`late ${status} refresh from account A cannot replace or log out account B`, async ({ page }) => {
    const held = await hold(page, "auth/refresh");
    await boot(page, { jwt: token({}, 60) });
    await start(page);
    await started(held);
    await mockLogin(page);
    await login(page);
    expect((await result(page)).code).toBe("ERR_CANCELED");
    await held.release(status === 200 ? { access_token: token({}, 7200), user: userA }
      : { detail: "Invalid or expired token" }, status);
    await expect(page.getByTestId("private-user")).toHaveText(userB.username);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem("authUser")))).toEqual(userB);
    await start(page, "next");
    await result(page, "next", true);
  });

  test(`late ${status} private response is rejected after an account switch`, async ({ page }) => {
    const held = await hold(page, "synthetic-private");
    await boot(page);
    await start(page);
    await started(held);
    await mockLogin(page);
    await login(page);
    await held.release(status === 200 ? { private: "SYNTHETIC-ACCOUNT-A" }
      : { detail: "Invalid or expired token" }, status);
    expect((await result(page)).code).toBe("ERR_CANCELED");
    await expect(page.getByTestId("private-user")).toHaveText(userB.username);
    expect(await page.evaluate(() => window.authTest.results.pending.data)).toBeUndefined();
  });
}

test("a queued request keeps its invoking identity through a synchronous logout/login", async ({ page }) => {
  await boot(page);
  await mockLogin(page);
  const authorizations = [];
  await page.route("**/api/synthetic-private", route => {
    authorizations.push(route.request().headers().authorization);
    return route.fulfill({ json: {} });
  });
  await page.evaluate(async () => {
    window.authTest.start("queued", "/synthetic-private");
    await window.authTest.api.login({ username: "synthetic", password: "synthetic-password" });
  });
  expect((await result(page, "queued")).code).toBe("ERR_CANCELED");
  await expect(page.getByTestId("private-user")).toHaveText(userB.username);
  // An already dispatched A request may reach the mock, but never carries B's credentials.
  expect(authorizations.length).toBeLessThanOrEqual(1);
  expect(authorizations).not.toContain(`Bearer ${tokenB()}`);
  expect(authorizations.every(header => JSON.parse(Buffer.from(header.split(".")[1], "base64url")).sub === "9001")).toBe(true);
});

test("a stale refresh finalizer cannot clear the new account's single-flight refresh", async ({ page }) => {
  const old = await hold(page, "auth/refresh");
  await boot(page, { jwt: token({}, 60) });
  await start(page, "old");
  await started(old);
  await mockLogin(page, tokenB(60));
  await login(page);
  const current = await hold(page, "auth/refresh");
  await start(page, "new-one");
  await started(current);
  await old.release({ access_token: token({}, 7200), user: userA });
  await start(page, "new-two");
  await current.release({ access_token: tokenB(7200), user: userB });
  await result(page, "new-one", true);
  await result(page, "new-two", true);
  expect(current.requests).toHaveLength(1);
});

test("cross-tab logout removes the real candidate UI, clears drafts and cancels requests", async ({ page, context }) => {
  await boot(page, { app: true });
  await entry(page).click();
  await correction(page).fill("SYNTHETIC-UNSAVED");
  await expect.poll(() => page.evaluate(() => JSON.stringify(sessionStorage))).toContain("SYNTHETIC-UNSAVED");
  const held = await hold(page, "synthetic-private");
  await page.evaluate(async () => {
    const { apiClient } = await import("/auth-session-api.js");
    window.pendingResult = null;
    apiClient.get("/synthetic-private").then(() => { window.pendingResult = "accepted"; }, error => { window.pendingResult = error.code; });
  });
  await started(held);
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await tab.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByTestId("candidate-detail")).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => window.pendingResult)).toBe("ERR_CANCELED");
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain("SYNTHETIC-UNSAVED");
  await held.release({ private: "SYNTHETIC-ACCOUNT-A" });
});

test("cross-tab account change remounts private state and updates user and role", async ({ page, context }) => {
  await boot(page);
  await page.getByLabel("Unsaved correction").fill("PRIVATE-ALPHA");
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await mockLogin(tab);
  await login(tab);
  await expect(page.getByTestId("private-user")).toHaveText(userB.username);
  await expect(page.getByTestId("private-role")).toHaveText(userB.role);
  await expect(page.getByLabel("Unsaved correction")).toHaveValue("");
  await expect(page.getByTestId("private-mount")).not.toHaveText("1");
});

for (const mode of ["clear", "token", "user"]) {
  test(`cross-tab ${mode} removal fails closed`, async ({ page, context }) => {
    await boot(page);
    const tab = await context.newPage();
    await tab.goto("/auth-test");
    await tab.evaluate(mode => {
      if (mode === "clear") localStorage.clear();
      else localStorage.removeItem(mode === "token" ? "authToken" : "authUser");
    }, mode);
    await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
    await expect(page.getByTestId("private-panel")).toHaveCount(0);
  });
}

test("same-session refresh synchronizes React without remounting or losing local edits", async ({ page }) => {
  const renewed = token({}, 7200);
  const refreshedUser = { ...userA, full_name: "Synthetic refreshed name" };
  const held = await hold(page, "auth/refresh");
  await boot(page, { jwt: token({}, 60) });
  await page.getByLabel("Unsaved correction").fill("KEEP-ME");
  await start(page, "one");
  await start(page, "two");
  await started(held);
  await held.release({ access_token: renewed, user: refreshedUser });
  await result(page, "one", true);
  await result(page, "two", true);
  expect(held.requests).toHaveLength(1);
  await expect(page.getByTestId("token")).toHaveText(renewed);
  await expect(page.getByTestId("private-mount")).toHaveText("1");
  await expect(page.getByLabel("Unsaved correction")).toHaveValue("KEEP-ME");
  expect(await page.evaluate(() => window.authTest.auth.user.full_name)).toBe(refreshedUser.full_name);
});

test("another tab's successful refresh wins over a late refresh failure", async ({ page, context }) => {
  const renewed = token({}, 7200);
  const held = await hold(page, "auth/refresh");
  await boot(page, { jwt: token({}, 60) });
  await page.getByLabel("Unsaved correction").fill("KEEP-ACROSS-TABS");
  await start(page);
  await started(held);
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await tab.route("**/api/auth/refresh", route => route.fulfill({ json: { access_token: renewed, user: userA } }));
  await start(tab, "refreshing-tab");
  await result(tab, "refreshing-tab", true);
  await expect(page.getByTestId("token")).toHaveText(renewed);
  await held.release({ detail: "Invalid or expired token" }, 401);
  await result(page, "pending", true);
  await expect(page.getByLabel("Unsaved correction")).toHaveValue("KEEP-ACROSS-TABS");
  await expect(page.getByTestId("private-mount")).toHaveText("1");
});

for (const sidless of [false, true]) {
  test(`${sidless ? "sidless fallback" : "stable sid"} preserves actual review corrections across refresh and reload`, async ({ page }) => {
    const claims = sidless ? { sid: undefined, ver: undefined, iat: 100 } : {};
    await boot(page, { app: true, jwt: token(claims) });
    await entry(page).click();
    await correction(page).fill("SYNTHETIC-UNSAVED");
    await expect.poll(() => page.evaluate(() => JSON.stringify(sessionStorage))).toContain("SYNTHETIC-UNSAVED");
    const renewed = token({ ...claims, iat: 200 }, 7200);
    await page.route("**/api/auth/refresh", route => route.fulfill({ json: { access_token: renewed, user: userA } }));
    await page.evaluate(async nearExpiry => {
      localStorage.setItem("authToken", nearExpiry);
      const { apiClient } = await import("/auth-session-api.js");
      await apiClient.get("/synthetic-refresh-trigger");
    }, token(claims, 60));
    await expect(correction(page)).toHaveValue("SYNTHETIC-UNSAVED");
    await page.reload();
    await entry(page).click();
    await expect(correction(page)).toHaveValue("SYNTHETIC-UNSAVED");
  });
}

test("real same-user login resets sidless identity even for an identical token", async ({ page }) => {
  const jwt = token({ sid: undefined, ver: undefined });
  await boot(page, { jwt });
  await page.getByLabel("Unsaved correction").fill("OLD-LOGIN");
  const before = await page.evaluate(() => {
    const identity = window.authTest.api.reviewDraftSession(localStorage.getItem("authToken"));
    sessionStorage.setItem('parcer:intake-review:v1:synthetic', 'OLD-LOGIN');
    return identity;
  });
  await mockLogin(page, jwt, userA);
  await login(page);
  const after = await page.evaluate(() => window.authTest.api.reviewDraftSession(localStorage.getItem("authToken")));
  expect(after).not.toBe(before);
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain("OLD-LOGIN");
  await expect(page.getByLabel("Unsaved correction")).toHaveValue("");
  await page.reload();
  expect(await page.evaluate(() => window.authTest.api.reviewDraftSession(localStorage.getItem("authToken")))).toBe(after);
});

for (const changed of [{ sid: "new-login" }, { ver: "new-password-version" }]) {
  test(`a changed ${Object.keys(changed)[0]} cannot masquerade as a refresh`, async ({ page }) => {
    await boot(page, { jwt: token({}, 60) });
    await page.route("**/api/auth/refresh", route => route.fulfill({ json: { access_token: token(changed), user: userA } }));
    await start(page);
    await result(page);
    await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
  });
}

test("detached review effects cannot reopen an old draft session after logout", async ({ page }) => {
  await boot(page);
  const checks = await page.evaluate(() => {
    const { api, drafts } = window.authTest;
    const old = api.reviewDraftSession(localStorage.getItem("authToken"));
    api.logout();
    return {
      sync: drafts.syncReviewDraftSession(old),
      write: drafts.writeReviewDrafts("parcer:intake-review:v1:synthetic", [], []),
      storage: JSON.stringify(sessionStorage),
    };
  });
  expect(checks.sync).toBe(false);
  expect(checks.write).toBe(false);
  expect(checks.storage).not.toContain("parcer:intake-review");
});

test("a late login is invalidated by logout in an already signed-out second tab", async ({ page, context }) => {
  await boot(page, { jwt: null, user: null });
  const held = await hold(page, "auth/login");
  await page.evaluate(() => {
    window.authTest.auth.login("synthetic", "synthetic-password").then(
      () => { window.authTest.results.login = { ok: true }; },
      error => { window.authTest.results.login = { ok: false, code: error.code }; },
    );
  });
  await started(held);
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await tab.getByRole("button", { name: "Sign out" }).click();
  expect((await result(page, "login")).code).toBe("ERR_CANCELED");
  await held.release({ access_token: token(), user: userA });
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
});

test("current-session 401 revocation logs out React and clears credentials", async ({ page }) => {
  await boot(page);
  await page.route("**/api/synthetic-private", route => route.fulfill({ status: 401, json: { detail: "Session revoked" } }));
  await start(page);
  await result(page);
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
});

test("malformed user storage cannot render an authenticated view", async ({ page }) => {
  await boot(page);
  await page.evaluate(() => localStorage.setItem("authUser", "not-json"));
  await page.reload();
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
});

test("questionnaire and CV upload timeouts cover the bounded parser deadline", async ({ page }) => {
  await boot(page);
  const captured = await page.evaluate(async () => {
    const seen = [];
    window.authTest.api.apiClient.defaults.adapter = async config => {
      seen.push({ url: config.url, timeout: config.timeout });
      return { config, data: {}, status: 200, statusText: "OK", headers: {} };
    };
    const synthetic = new File(["synthetic"], "synthetic.txt", { type: "text/plain" });
    await window.authTest.api.uploadCandidateFile(synthetic);
    await window.authTest.api.uploadCvFile(synthetic);
    return seen;
  });
  expect(captured).toEqual([{ url: "/upload", timeout: 120000 }, { url: "/upload_cv", timeout: 120000 }]);
});

test("failed login keeps the real form mounted and displays its error", async ({ page }) => {
  await boot(page, { jwt: null, user: null });
  await page.goto("/login");
  await page.route("**/api/auth/login", route => route.fulfill({ status: 401, json: { detail: "Invalid credentials" } }));
  await page.locator("#username").fill("synthetic-invalid");
  await page.locator("#password").fill("synthetic-password");
  await page.getByTestId("login-form").locator("button").click();
  await expect(page.getByTestId("login-form").locator(".error")).toBeVisible();
  await expect(page.locator("#username")).toHaveValue("synthetic-invalid");
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
});

test("successful login through the real form establishes the new session", async ({ page }) => {
  await boot(page, { jwt: null, user: null });
  await page.goto("/login");
  await mockLogin(page);
  await page.locator("#username").fill("synthetic-beta");
  await page.locator("#password").fill("synthetic-password");
  await page.getByTestId("login-form").locator("button").click();
  await expect(page).toHaveURL(/\/menu$/);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("authUser")))).toEqual(userB);
});

test("cross-tab logout cancels a held refresh before it can restore storage", async ({ page, context }) => {
  const held = await hold(page, "auth/refresh");
  await boot(page, { jwt: token({}, 60) });
  await start(page);
  await started(held);
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await tab.getByRole("button", { name: "Sign out" }).click();
  expect((await result(page)).code).toBe("ERR_CANCELED");
  await held.release({ access_token: token({}, 7200), user: userA });
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
});

test("late private 401 cannot invalidate a renewed token in the same session", async ({ page, context }) => {
  const held = await hold(page, "synthetic-private");
  await boot(page);
  await start(page);
  await started(held);
  const renewed = token({}, 7200);
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await tab.evaluate(jwt => localStorage.setItem("authToken", jwt), renewed);
  await expect(page.getByTestId("token")).toHaveText(renewed);
  await held.release({ detail: "Invalid or expired token" }, 401);
  await result(page);
  await expect(page.getByTestId("private-user")).toHaveText(userA.username);
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBe(renewed);
});

test("a changed server version remounts private state and clears drafts", async ({ page, context }) => {
  await boot(page);
  await page.getByLabel("Unsaved correction").fill("OLD-VERSION");
  await page.evaluate(() => sessionStorage.setItem("parcer:intake-review:v1:synthetic", "OLD-VERSION"));
  const tab = await context.newPage();
  await tab.goto("/auth-test");
  await tab.evaluate(jwt => localStorage.setItem("authToken", jwt), token({ ver: "new-version" }));
  await expect(page.getByLabel("Unsaved correction")).toHaveValue("");
  expect(await page.evaluate(() => JSON.stringify(sessionStorage))).not.toContain("OLD-VERSION");
});

test("caller cancellation is preserved without logging out the current session", async ({ page }) => {
  const held = await hold(page, "synthetic-private");
  await boot(page);
  await page.evaluate(() => {
    window.callerAbort = new AbortController();
    window.authTest.start("abortable", "/synthetic-private", { signal: window.callerAbort.signal });
  });
  await started(held);
  await page.evaluate(() => window.callerAbort.abort());
  expect((await result(page, "abortable")).code).toBe("ERR_CANCELED");
  await expect(page.getByTestId("private-user")).toHaveText(userA.username);
  await held.release({ synthetic: true });
});

test("a pending renewal crosses expiry without losing real review drafts or sending expired private requests", async ({ page }) => {
  const now = Date.now();
  await page.clock.setFixedTime(now);
  await boot(page, { app: true });
  await entry(page).click();
  await correction(page).fill("KEEP-THROUGH-EXPIRY");
  await expect.poll(() => page.evaluate(() => JSON.stringify(sessionStorage))).toContain("KEEP-THROUGH-EXPIRY");
  const held = await hold(page, "auth/refresh");
  const headers = [];
  await page.route("**/api/synthetic-private", route => {
    headers.push(route.request().headers().authorization);
    return route.fulfill({ json: {} });
  });
  await page.evaluate(async jwt => {
    localStorage.setItem("authToken", jwt);
    const { apiClient } = await import("/auth-session-api.js");
    window.expiryResults = [];
    window.startExpiryRequest = () => apiClient.get("/synthetic-private").then(
      () => { window.expiryResults.push("accepted"); }, error => { window.expiryResults.push(error.code); });
    void window.startExpiryRequest();
  }, token({ exp: Math.floor(now / 1000) + 2 }));
  await started(held);
  await page.clock.setFixedTime(now + 3000);
  await page.evaluate(() => {
    window.dispatchEvent(new Event("focus"));
    void window.startExpiryRequest();
  });
  await expect(correction(page)).toHaveValue("KEEP-THROUGH-EXPIRY");
  expect(headers).toEqual([]);
  const renewed = token({}, 7200);
  await held.release({ access_token: renewed, user: userA });
  await expect.poll(() => page.evaluate(() => window.expiryResults)).toEqual(["accepted", "accepted"]);
  expect(headers).toEqual([`Bearer ${renewed}`, `Bearer ${renewed}`]);
  expect(held.requests).toHaveLength(1);
  await page.reload();
  await entry(page).click();
  await expect(correction(page)).toHaveValue("KEEP-THROUGH-EXPIRY");
});

for (const status of [401, 500]) {
  test(`failed renewal after expiry (${status}) still clears authentication`, async ({ page }) => {
    const now = Date.now();
    await page.clock.setFixedTime(now);
    const held = await hold(page, "auth/refresh");
    await boot(page, { jwt: token({ exp: Math.floor(now / 1000) + 2 }) });
    await start(page);
    await started(held);
    await page.clock.setFixedTime(now + 3000);
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await held.release({ detail: "Synthetic renewal failure" }, status);
    await result(page);
    await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
  });
}

for (const change of ["logout", "login"]) {
  test(`cross-tab ${change} invalidates a renewal even after its old token expires`, async ({ page, context }) => {
    const now = Date.now();
    await page.clock.setFixedTime(now);
    const held = await hold(page, "auth/refresh");
    await boot(page, { jwt: token({ exp: Math.floor(now / 1000) + 2 }) });
    await start(page);
    await started(held);
    await page.clock.setFixedTime(now + 3000);
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    const tab = await context.newPage();
    await tab.goto("/auth-test");
    if (change === "login") {
      await mockLogin(tab);
      await login(tab);
    } else {
      await tab.getByRole("button", { name: "Sign out" }).click();
    }
    expect((await result(page)).code).toBe("ERR_CANCELED");
    await held.release({ access_token: token({}, 7200), user: userA });
    if (change === "login") {
      await expect(page.getByTestId("private-user")).toHaveText(userB.username);
    } else {
      await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
      expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
    }
  });
}

test("an expired token at startup cannot use the pending-renewal exception", async ({ page }) => {
  await boot(page, { jwt: token({}, -10) });
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
  await expect(page.getByTestId("private-panel")).toHaveCount(0);
});

test("pending renewal cannot install an already expired replacement token", async ({ page }) => {
  const now = Date.now();
  await page.clock.setFixedTime(now);
  const held = await hold(page, "auth/refresh");
  await boot(page, { jwt: token({ exp: Math.floor(now / 1000) + 2 }) });
  await start(page);
  await started(held);
  await page.clock.setFixedTime(now + 3000);
  await held.release({ access_token: token({ exp: Math.floor(now / 1000) + 1 }), user: userA });
  await result(page);
  await expect(page.getByRole("heading", { name: "Signed out" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("authToken"))).toBeNull();
});
