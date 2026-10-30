// One clip at a time across every play button: starting a clip stops the
// previous one, whatever kind of button started it.

let stopCurrent: (() => void) | null = null;

export function takeFocus(stop: () => void): void {
  if (stopCurrent && stopCurrent !== stop) stopCurrent();
  stopCurrent = stop;
}

export function releaseFocus(stop: () => void): void {
  if (stopCurrent === stop) stopCurrent = null;
}
