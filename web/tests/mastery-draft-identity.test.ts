import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * #1412 / #1392 — a mastery draft is not a stable identity.
 *
 * A bare `/mastery/:pathId/sessions` route does not open a server session. It
 * opens a **local** draft whose server session is created implicitly inside
 * the first turn's `start_turn`, so "which conversation am I in?" is entirely
 * a client-side identity, and nothing on the server can repair it once the
 * client loses track.
 *
 * Two ways the client loses track, both visible in the source below:
 *
 *   - The route resolves its draft once, guarded by a `useRef` marker
 *     (`initializedRouteRef`). A ref is scoped to a single mount, so a
 *     remount — StrictMode's deliberate double-invoke, a fast topic switch, a
 *     remount of the `[pathId]/sessions` layout — forgets the marker and mints
 *     a *second* draft. Two drafts become two server sessions from one learner
 *     intent (#1412).
 *   - `ensureSelectedSession` fabricates an entry under the fixed key
 *     `"draft"`, which no reducer transition ever puts into `state.sessions`.
 *     Anything that reads the adapter before a real draft exists is handed a
 *     phantom session, and the next dispatch that trusts it has to mint yet
 *     another entry.
 *
 * #1392 is the same missing identity seen from the panel: `SessionCamp` is
 * handed `sessions` and nothing else, so a path holding a live, configured
 * draft that has not sent a message yet renders "No sessions yet" — a false
 * and alarming claim to the learner who just started one.
 *
 * The first three tests are expected to fail until WP-C step 2 lands the fix.
 * The last two guard invariants that fix must not break.
 */

const adapter = readFileSync("features/chat/ChatStateAdapter.tsx", "utf8");
const sessionHook = readFileSync("hooks/useMasteryStudySession.ts", "utf8");
const sessionCamp = readFileSync(
  "components/space/learning/SessionCamp.tsx",
  "utf8",
);
const masteryPage = readFileSync(
  "app/(utility)/mastery/[pathId]/page.tsx",
  "utf8",
);

/* ── reproductions ──────────────────────────────────────────────────────── */

test("a remounted route reuses the draft it already opened instead of minting another", () => {
  assert.doesNotMatch(
    sessionHook,
    /initializedRouteRef/,
    "draft bookkeeping is pinned to a useRef, which is thrown away on remount, so re-entering the route opens a second draft (#1412)",
  );
  assert.doesNotMatch(
    sessionHook,
    /newSession\(courseSessionConfiguration\(sessionConfiguration, courseId\)\)/,
    "the bare-route branch creates a draft unconditionally; it must reuse the route's existing unsubmitted draft first",
  );
});

test("no session entry is fabricated for a key that is not in state.sessions", () => {
  assert.doesNotMatch(
    adapter,
    /createSessionEntry\("draft"\)/,
    'ensureSelectedSession invents a session under the literal key "draft" that no reducer transition ever registered, so the adapter can report a session the rest of the reducer cannot see',
  );
});

test("the session panel is told about an unsubmitted draft so it cannot claim there are none", () => {
  assert.match(
    sessionCamp,
    /draft/i,
    "SessionCamp has no notion of a draft, so a path with a live draft but no committed session renders the empty state",
  );
  assert.match(
    masteryPage,
    /<SessionCamp[\s\S]{0,400}?draft/i,
    "the mastery page must hand the panel the draft it is currently holding, or the panel cannot tell a new path from an empty one (#1392)",
  );
});

/* ── guards: invariants the fix must preserve ───────────────────────────── */

test("a draft's path binding always comes from the route", () => {
  assert.match(
    sessionHook,
    /const currentRouteKey = `\$\{pathId\}/,
    "the route key must carry the topic, so bookkeeping can never be shared across topics",
  );
  assert.match(
    sessionHook,
    /masteryPathId: pathId,/,
    "the draft's configuration must be derived from the route param, never carried over from a previously configured session",
  );
});

test("a reloaded route rebuilds the same binding from the URL alone", () => {
  assert.doesNotMatch(
    sessionHook,
    /localStorage|sessionStorage/,
    "the binding must be reconstructible from the route; parking it in storage would let a stale draft outlive its topic",
  );
  assert.match(sessionHook, /isMasteryDraftSessionReady/);
  assert.match(
    sessionHook,
    /\/mastery\/\$\{encodeURIComponent\(pathId\)\}/,
    "promotion must write the topic and session into the URL, which is what makes the binding survive a reload",
  );
});
