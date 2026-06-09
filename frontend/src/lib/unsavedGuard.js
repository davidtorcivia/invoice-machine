import { beforeNavigate } from '$app/navigation';

/**
 * Warn before navigating away from a form with unsaved edits.
 *
 * Call at component init. `getState` should return a stable serialization of the
 * form (e.g. JSON.stringify of the bound fields). After loading initial data call
 * `snapshot()`, and before a programmatic navigation that follows a successful
 * save call `allowLeave()` so the guard doesn't fire on the redirect.
 *
 * @param {() => string} getState
 */
export function createUnsavedGuard(getState) {
  let initial = '';
  let allow = false;

  beforeNavigate((nav) => {
    const dirty = !allow && initial !== '' && getState() !== initial;
    if (dirty && !confirm('You have unsaved changes. Leave without saving?')) {
      nav.cancel();
    }
  });

  return {
    /** Capture the current form state as the clean baseline. */
    snapshot() {
      initial = getState();
    },
    /** Suppress the guard for the next navigation (e.g. post-save redirect). */
    allowLeave() {
      allow = true;
    }
  };
}
