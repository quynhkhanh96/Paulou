import { guideAudioUrl } from "./api";
import { GUIDE, type Sound } from "./guideData";
import { PlayButton } from "./PlayButton";

function SoundCard({ sound }: { sound: Sound }) {
  return (
    <article className="glass sound">
      <h3 className={`sound-symbol ${sound.symbol.startsWith("/") ? "" : "is-label"}`} lang="fr">
        {sound.symbol}
      </h3>
      <p className="sound-how">{sound.how}</p>
      {sound.spelling && (
        <p className="sound-spelling">
          <strong>Spelled:</strong> {sound.spelling}
        </p>
      )}
      {sound.tip && <p className="note hint">{sound.tip}</p>}
      {sound.examples.length > 0 && (
        <ul className="examples-list" aria-label="Examples">
          {sound.examples.map((example) => (
            <li key={example.word}>
              <PlayButton compact src={guideAudioUrl(example.word)} label={`Listen to "${example.word}"`} />
              <span className="example-word" lang="fr">
                {example.word}
              </span>
              <span className="unit-ipa">/{example.ipa}/</span>
              <span className="example-gloss"> {example.gloss}</span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function Guide() {
  const jump = (id: string) => {
    document.getElementById(`guide-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  return (
    <div className="guide">
      <section className="glass guide-intro">
        <h2>Pronunciation guide</h2>
        <p>
          The sounds of standard (Parisian) French, with how to make each one and examples. Sounds are written in IPA
          between slashes, the same symbols you see in your results. Regional accents differ.
        </p>
        <nav aria-label="Guide sections" className="guide-jump">
          {GUIDE.map((section) => (
            <button key={section.id} type="button" className="link" onClick={() => jump(section.id)}>
              {section.title}
            </button>
          ))}
        </nav>
      </section>
      {GUIDE.map((section) => (
        <section key={section.id} id={`guide-${section.id}`} aria-labelledby={`guide-${section.id}-title`} className="guide-section">
          <h2 id={`guide-${section.id}-title`}>{section.title}</h2>
          <p className="note">{section.intro}</p>
          <div className="sound-grid">
            {section.sounds.map((sound) => (
              <SoundCard key={sound.id} sound={sound} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
