import { useEffect, useState } from "react";

export function Loading({ onCancel }: { onCancel: () => void }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <section className="glass loading" role="status" aria-live="polite">
      <div className="orb" aria-hidden="true" />
      <h2>Preparing your sentence</h2>
      <p>
        Splitting it into rhythm groups and recording a reference voice. Short sentences take a few seconds, longer
        ones up to about 15.
      </p>
      <p className="elapsed">{seconds} s</p>
      <button type="button" className="btn btn-soft" onClick={onCancel}>
        Cancel
      </button>
    </section>
  );
}
