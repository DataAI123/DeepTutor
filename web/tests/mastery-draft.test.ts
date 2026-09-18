import assert from "node:assert/strict";
import test from "node:test";

import {
  masteryDraftFor,
  masteryDraftIdentityKey,
  releaseMasteryDraft,
  trackMasteryDraft,
} from "../lib/mastery-draft";

/* ── identity ───────────────────────────────────────────────────────────── */

test("one request is one identity, however it is spelled", () => {
  const identity = {
    masteryPathId: "topic-a",
    masterySessionMode: "review" as const,
    courseId: "course-1",
  };
  assert.equal(
    masteryDraftIdentityKey(identity),
    masteryDraftIdentityKey({
      masteryPathId: " topic-a ",
      masterySessionMode: "review",
      courseId: "course-1 ",
    }),
  );
});

test("a different topic, mode or course is a different conversation", () => {
  const base = {
    masteryPathId: "topic-a",
    masterySessionMode: "study" as const,
    courseId: "",
  };
  const keys = [
    masteryDraftIdentityKey(base),
    masteryDraftIdentityKey({ ...base, masteryPathId: "topic-b" }),
    masteryDraftIdentityKey({ ...base, masterySessionMode: "outline" }),
    masteryDraftIdentityKey({ ...base, courseId: "course-1" }),
  ];
  assert.equal(new Set(keys).size, keys.length);
});

test("a blank course scope is the same request as no course", () => {
  assert.equal(
    masteryDraftIdentityKey({
      masteryPathId: "topic-a",
      masterySessionMode: "study",
      courseId: "   ",
    }),
    masteryDraftIdentityKey({
      masteryPathId: "topic-a",
      masterySessionMode: "study",
      courseId: "",
    }),
  );
});

/* ── the open-draft registry ────────────────────────────────────────────── */

test("a draft is reachable by request, and re-tracking it is idempotent", () => {
  const identity = {
    masteryPathId: "registry-idempotent",
    masterySessionMode: "study" as const,
    courseId: "",
  };
  assert.equal(masteryDraftFor(identity), null);

  const first = trackMasteryDraft(identity, "draft-key-1");
  assert.equal(first.sessionKey, "draft-key-1");
  assert.equal(first.startedAt > 0, true);

  const again = trackMasteryDraft(identity, "draft-key-1");
  assert.equal(again, first);
  assert.equal(again.startedAt, first.startedAt);
});

test("a remount re-attaches to the key the adapter is actually holding", () => {
  const identity = {
    masteryPathId: "registry-reattach",
    masterySessionMode: "outline" as const,
    courseId: "course-9",
  };
  const first = trackMasteryDraft(identity, "draft-key-old");
  const second = trackMasteryDraft(identity, "draft-key-new");

  assert.equal(second.sessionKey, "draft-key-new");
  assert.equal(second.startedAt, first.startedAt);
  assert.equal(masteryDraftFor(identity)?.sessionKey, "draft-key-new");
});

test("releasing one key leaves every other identity alone", () => {
  const released = {
    masteryPathId: "registry-release",
    masterySessionMode: "study" as const,
    courseId: "",
  };
  const kept = {
    masteryPathId: "registry-keep",
    masterySessionMode: "study" as const,
    courseId: "",
  };
  trackMasteryDraft(released, "draft-key-shared");
  trackMasteryDraft(kept, "draft-key-kept");

  releaseMasteryDraft("draft-key-shared");

  assert.equal(masteryDraftFor(released), null);
  assert.equal(masteryDraftFor(kept)?.sessionKey, "draft-key-kept");

  releaseMasteryDraft("draft-key-kept");
  assert.equal(masteryDraftFor(kept), null);
});
