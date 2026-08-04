/**
 * Toast store unit tests.
 *
 * The toast store is the human-feedback channel parallel to `apiLogs`.
 * These tests pin down the ring-buffer cap (5), auto-increment ids and the
 * dismiss semantics so a future refactor can't silently flood the screen
 * or leak stale toasts across sessions.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { useToastStore, toast } from '../store/toastStore';

describe('toastStore', () => {
  beforeEach(() => {
    useToastStore.getState().clear();
  });

  it('push adds a toast with an incrementing id and default ttl', () => {
    const id = useToastStore.getState().push('success', 'First');
    const state = useToastStore.getState();
    expect(state.toasts).toHaveLength(1);
    expect(state.toasts[0].id).toBe(id);
    expect(state.toasts[0].kind).toBe('success');
    expect(state.toasts[0].ttlMs).toBe(4000);
  });

  it('caps the visible stack at 5 toasts (drops oldest)', () => {
    for (let i = 0; i < 8; i++) useToastStore.getState().push('info', `t${i}`);
    const { toasts } = useToastStore.getState();
    expect(toasts).toHaveLength(5);
    expect(toasts[0].message).toBe('t3'); // first 3 dropped
    expect(toasts[4].message).toBe('t7');
  });

  it('dismiss removes a single toast by id', () => {
    const id1 = useToastStore.getState().push('info', 'a');
    const id2 = useToastStore.getState().push('info', 'b');
    useToastStore.getState().dismiss(id1);
    const { toasts } = useToastStore.getState();
    expect(toasts.map((t) => t.id)).toEqual([id2]);
  });

  it('imperative helpers route through the store', () => {
    toast.success('saved');
    toast.error('boom');
    toast.info('fyi');
    const kinds = useToastStore.getState().toasts.map((t) => t.kind);
    expect(kinds).toEqual(['success', 'error', 'info']);
    // errors default to a longer ttl (6000) to give time to read
    const err = useToastStore.getState().toasts.find((t) => t.kind === 'error');
    expect(err?.ttlMs).toBe(6000);
  });
});
