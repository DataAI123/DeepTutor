"use client";

import { useMemo, useSyncExternalStore } from "react";

import { DEFAULT_MASTERY_MODE, type MasteryMode } from "@/lib/mastery-mode";

/**
 * The unsubmitted mastery drafts that are currently open — the client's
 * memory of "this route has already started something".
 *
 * A bare `/mastery/:pathId/sessions` route opens no server session. It opens
 * a *local* draft: the conversation itself is created implicitly inside the
 * first turn's `start_turn`, so until that message is sent, the only thing
 * saying a conversation is underway is client state. Nothing in the runtime
 * survives a move between the topic page and the sessions surface, so a
 * record kept in a component — the `useRef` this replaces — is discarded
 * exactly when it is next needed, and re-entering the route mints a second
 * draft and, from one learner intent, a second server session (#1412).
 *
 * Module scope, and in memory only.
 *
 * In memory because an unsubmitted draft has no server state at all: after a
 * reload there is genuinely nothing to restore, and persisting the *binding*
 * would let a draft outlive the topic it belongs to — the invariant the
 * study hook's `isMasteryDraftSessionReady` guard exists to protect.
 *
 * Module scope because the two readers sit on opposite sides of the runtime.
 * The study hook opens the draft from inside `ChatRuntimeProvider`; the topic
 * page's sessions panel renders outside it, and still has to be able to tell
 * "a draft is live here" from "this topic is empty" (#1392).
 */

/** What the learner asked for. Identity is the request, not the row. */
export interface MasteryDraftIdentity {
  masteryPathId: string;
  masterySessionMode: MasteryMode;
  courseId: string;
}

export interface MasteryDraftRecord {
  masteryPathId: string;
  masterySessionMode: MasteryMode;
  courseId: string;
  /**
   * The adapter's key for this draft. This is what lets a remount *re-attach*
   * to the draft instead of opening another one: the adapter that comes back
   * has an empty session map, and only this key names the entry to rebuild.
   */
  sessionKey: string;
  startedAt: number;
}

/**
 * Two visits that agree on topic, mode and course scope are the same intent
 * and must share one draft. Disagreeing on any of them is a conversation the
 * learner deliberately opened — an outline and a review on one topic, or the
 * same topic in two courses, are three separate drafts.
 *
 * The topic is part of the key rather than a separate lookup so bookkeeping
 * can never be shared across topics.
 */
export function masteryDraftIdentityKey(identity: MasteryDraftIdentity): string {
  return [
    identity.masteryPathId.trim(),
    identity.masterySessionMode || DEFAULT_MASTERY_MODE,
    identity.courseId.trim(),
  ].join("\u0000");
}

const drafts = new Map<string, MasteryDraftRecord>();

const listeners = new Set<() => void>();

/**
 * `useSyncExternalStore` compares snapshots by identity, so each change
 * publishes a new map; `drafts` is mutated in place and would always look
 * unchanged. Readers derive from this map rather than from the live one, so
 * a render can never observe a change the store has not announced yet.
 */
let snapshot: ReadonlyMap<string, MasteryDraftRecord> = new Map();

const EMPTY_SNAPSHOT: ReadonlyMap<string, MasteryDraftRecord> = new Map();

function getSnapshot(): ReadonlyMap<string, MasteryDraftRecord> {
  return snapshot;
}

function getServerSnapshot(): ReadonlyMap<string, MasteryDraftRecord> {
  return EMPTY_SNAPSHOT;
}

function emit(): void {
  snapshot = new Map(drafts);
  for (const listener of listeners) listener();
}

/** The draft already open for this identity, or null. */
export function masteryDraftFor(
  identity: MasteryDraftIdentity,
): MasteryDraftRecord | null {
  return drafts.get(masteryDraftIdentityKey(identity)) ?? null;
}

/**
 * Record that this identity is now held by `sessionKey`.
 *
 * Idempotent by identity: re-tracking the same pair keeps the original
 * `startedAt`, so a remount is not mistaken for a fresh start. A *different*
 * key for the same identity replaces the old record — the adapter is the
 * authority on which key is live, and a stale key would send the next
 * remount looking for an entry that no longer exists.
 */
export function trackMasteryDraft(
  identity: MasteryDraftIdentity,
  sessionKey: string,
): MasteryDraftRecord {
  const identityKey = masteryDraftIdentityKey(identity);
  const existing = drafts.get(identityKey);
  if (existing && existing.sessionKey === sessionKey) return existing;

  const record: MasteryDraftRecord = {
    masteryPathId: identity.masteryPathId.trim(),
    masterySessionMode: identity.masterySessionMode || DEFAULT_MASTERY_MODE,
    courseId: identity.courseId.trim(),
    sessionKey,
    startedAt: existing?.startedAt ?? Date.now(),
  };
  drafts.set(identityKey, record);
  emit();
  return record;
}

/**
 * Drop a draft once the route names a server session.
 *
 * From that moment the conversation is the server's — it appears in the
 * topic's session list — and keeping a local copy would show the learner the
 * same conversation twice.
 */
export function releaseMasteryDraft(sessionKey: string): void {
  let removed = false;
  for (const [identityKey, record] of drafts) {
    if (record.sessionKey !== sessionKey) continue;
    drafts.delete(identityKey);
    removed = true;
  }
  if (removed) emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * The drafts a topic is holding, newest first.
 *
 * A list rather than a single record because a topic can hold several at
 * once: the panel opens study, outline and review drafts on the same goal,
 * and showing a row for each is what keeps the panel honest instead of
 * silently picking one.
 */
export function useMasteryDrafts(pathId: string): readonly MasteryDraftRecord[] {
  const open = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const topicId = pathId.trim();
  return useMemo(
    () =>
      Array.from(open.values())
        .filter((record) => record.masteryPathId === topicId)
        .sort((a, b) => b.startedAt - a.startedAt),
    [open, topicId],
  );
}
