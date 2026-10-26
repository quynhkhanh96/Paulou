// Static content of the Pronunciation guide (Decision Log D60). Standard
// (Parisian) French, IPA as used in the app's own results. Plain data: no
// pipeline, no network.

export interface Example {
  word: string;
  ipa: string;
  gloss: string;
}

export interface Sound {
  id: string;
  /** Shown large, already formatted: "/y/" or "/p/ · /t/ · /k/". */
  symbol: string;
  how: string;
  spelling?: string;
  tip?: string;
  examples: Example[];
}

export interface GuideSection {
  id: string;
  title: string;
  intro: string;
  sounds: Sound[];
}

const ex = (word: string, ipa: string, gloss: string): Example => ({ word, ipa, gloss });

export const GUIDE: GuideSection[] = [
  {
    id: "vowels",
    title: "Oral vowels",
    intro:
      "French vowels are pure: the lips and tongue hold one position and do not glide the way English \"go\" or \"day\" do. Lip rounding matters a lot.",
    sounds: [
      {
        id: "i",
        symbol: "/i/",
        how: "Like the \"ee\" in \"see\", but shorter and tenser, with the lips spread wide.",
        spelling: "i, î, y",
        examples: [ex("si", "si", "if"), ex("vie", "vi", "life"), ex("ici", "isi", "here")],
      },
      {
        id: "e",
        symbol: "/e/",
        how: "Closed \"e\". Like the vowel of \"day\" but without the glide at the end: keep the mouth still.",
        spelling: "é, final -er and -ez, ai in j'ai",
        examples: [ex("été", "ete", "summer"), ex("parler", "paʁle", "to speak"), ex("chez", "ʃe", "at (someone's)")],
      },
      {
        id: "epsilon",
        symbol: "/ɛ/",
        how: "Open \"e\", like the vowel of \"bed\".",
        spelling: "è, ê, ai, ei, e before a pronounced consonant",
        examples: [ex("mère", "mɛʁ", "mother"), ex("tête", "tɛt", "head"), ex("seize", "sɛz", "sixteen")],
      },
      {
        id: "a",
        symbol: "/a/",
        how: "A front \"a\", between the vowels of \"cat\" and \"father\". Mouth open, tongue forward.",
        spelling: "a, à",
        tip: "Some words have a darker /ɑ/ (pâte /pɑt/, âme /ɑm/). In everyday Parisian speech many people say /a/ for both.",
        examples: [ex("ami", "ami", "friend"), ex("là", "la", "there"), ex("pas", "pa", "not")],
      },
      {
        id: "open-o",
        symbol: "/ɔ/",
        how: "Open \"o\", like the vowel of British \"hot\" or of \"off\". Lips rounded.",
        spelling: "o before a pronounced consonant",
        examples: [ex("porte", "pɔʁt", "door"), ex("école", "ekɔl", "school"), ex("homme", "ɔm", "man")],
      },
      {
        id: "o",
        symbol: "/o/",
        how: "Closed \"o\". Round the lips and hold them still: no \"ow\" glide like English \"go\".",
        spelling: "o at the end of a word, ô, au, eau",
        examples: [ex("vélo", "velo", "bike"), ex("chaud", "ʃo", "hot"), ex("eau", "o", "water")],
      },
      {
        id: "u",
        symbol: "/u/",
        how: "Like the \"oo\" in \"food\", with the lips pushed forward into a small circle and the tongue pulled back.",
        spelling: "ou, où, oû",
        examples: [ex("vous", "vu", "you"), ex("nous", "nu", "we"), ex("ou", "u", "or")],
      },
      {
        id: "y",
        symbol: "/y/",
        how: "No English equivalent. Say /i/ (\"ee\") and, without moving your tongue, round your lips as for /u/.",
        spelling: "u, û",
        tip: "The classic pair is tu /ty/ versus tout /tu/: only the tongue position changes.",
        examples: [ex("tu", "ty", "you"), ex("rue", "ʁy", "street"), ex("sur", "syʁ", "on")],
      },
      {
        id: "o-slash",
        symbol: "/ø/",
        how: "Say /e/ and, without moving your tongue, round your lips. Closer to the vowel of German \"schön\".",
        spelling: "eu, œu at the end of a syllable or before /z/",
        examples: [ex("peu", "pø", "little"), ex("deux", "dø", "two"), ex("bleu", "blø", "blue")],
      },
      {
        id: "oe",
        symbol: "/œ/",
        how: "Say /ɛ/ (\"bed\") and round your lips. More open than /ø/.",
        spelling: "eu, œu before a pronounced consonant (except /z/)",
        examples: [ex("peur", "pœʁ", "fear"), ex("sœur", "sœʁ", "sister"), ex("fleur", "flœʁ", "flower")],
      },
      {
        id: "schwa",
        symbol: "/ə/",
        how: "A weak, slightly rounded vowel, close to the first vowel of \"about\" but with the lips rounded a little.",
        spelling: "e without an accent, in short words and syllables",
        tip: "It is often dropped in everyday speech (\"je ne sais pas\" can sound like \"j'ne sais pas\"). Paulou still counts a dropped schwa as missing.",
        examples: [ex("le", "lə", "the"), ex("je", "ʒə", "I"), ex("demain", "dəmɛ̃", "tomorrow")],
      },
    ],
  },
  {
    id: "nasals",
    title: "Nasal vowels",
    intro:
      "Air goes through the nose and the mouth at the same time. The \"n\" or \"m\" in the spelling is not pronounced as a consonant. There are four; many speakers merge /œ̃/ into /ɛ̃/.",
    sounds: [
      {
        id: "an",
        symbol: "/ɑ̃/",
        how: "Start from /a/ with the mouth open and lips slightly rounded, and let the air flow through the nose too.",
        spelling: "an, am, en, em",
        examples: [ex("enfant", "ɑ̃fɑ̃", "child"), ex("dans", "dɑ̃", "in"), ex("sans", "sɑ̃", "without")],
      },
      {
        id: "on",
        symbol: "/ɔ̃/",
        how: "Start from /o/ with the lips rounded, and let the air flow through the nose too.",
        spelling: "on, om",
        tip: "Compare bon /bɔ̃/ with bonne /bɔn/: when the n is followed by a vowel or doubled, it is a real consonant and the vowel is not nasal.",
        examples: [ex("bon", "bɔ̃", "good"), ex("nom", "nɔ̃", "name"), ex("on", "ɔ̃", "we, one")],
      },
      {
        id: "in",
        symbol: "/ɛ̃/",
        how: "Start from /ɛ/ (\"bed\") with the lips spread, and let the air flow through the nose too.",
        spelling: "in, im, ain, ein, (i)en",
        examples: [ex("vin", "vɛ̃", "wine"), ex("pain", "pɛ̃", "bread"), ex("bien", "bjɛ̃", "well")],
      },
      {
        id: "un",
        symbol: "/œ̃/",
        how: "Start from /œ/ with the lips rounded, and let the air flow through the nose too.",
        spelling: "un, um",
        tip: "Rare, and in Paris often pronounced as /ɛ̃/. Both are understood.",
        examples: [ex("un", "œ̃", "one"), ex("brun", "bʁœ̃", "brown"), ex("parfum", "paʁfœ̃", "perfume")],
      },
    ],
  },
  {
    id: "glides",
    title: "Semi-vowels",
    intro: "Short, quick sounds that glide into the next vowel. Each one is a very fast version of a vowel.",
    sounds: [
      {
        id: "j",
        symbol: "/j/",
        how: "Like the \"y\" in \"yes\".",
        spelling: "y, i before a vowel, -il(l) after a vowel",
        examples: [ex("yeux", "jø", "eyes"), ex("pied", "pje", "foot"), ex("travail", "tʁavaj", "work")],
      },
      {
        id: "w",
        symbol: "/w/",
        how: "Like the \"w\" in \"we\": a quick /u/ into the next vowel.",
        spelling: "ou before a vowel; oi is pronounced /wa/",
        examples: [ex("oui", "wi", "yes"), ex("moi", "mwa", "me"), ex("jouer", "ʒwe", "to play")],
      },
      {
        id: "hu",
        symbol: "/ɥ/",
        how: "A quick /y/ into the next vowel: say /i/ with your lips rounded as you glide. There is no English equivalent.",
        spelling: "u before a vowel",
        examples: [ex("huit", "ɥit", "eight"), ex("nuit", "nɥi", "night"), ex("lui", "lɥi", "him")],
      },
    ],
  },
  {
    id: "consonants",
    title: "Consonants",
    intro:
      "Many consonants are close to English. The ones below are where learners most often go wrong.",
    sounds: [
      {
        id: "ptk",
        symbol: "/p/ · /t/ · /k/",
        how: "Unaspirated: no puff of air, unlike English \"pie, tie, kie\". Hold a hand in front of your mouth: you should feel almost nothing. /t/ touches the back of the upper teeth, not the ridge behind them.",
        spelling: "p; t, th; c before a, o, u, qu, k",
        examples: [ex("papa", "papa", "dad"), ex("tout", "tu", "all"), ex("café", "kafe", "coffee")],
      },
      {
        id: "bdg",
        symbol: "/b/ · /d/ · /g/",
        how: "Voiced from the very start of the sound. /d/ touches the back of the upper teeth.",
        spelling: "b; d; g before a, o, u, gu before e, i",
        examples: [ex("beau", "bo", "beautiful"), ex("dos", "do", "back"), ex("gare", "gaʁ", "station")],
      },
      {
        id: "fv",
        symbol: "/f/ · /v/",
        how: "As in English.",
        spelling: "f, ph; v",
        examples: [ex("fou", "fu", "crazy"), ex("photo", "fɔto", "photo"), ex("vie", "vi", "life")],
      },
      {
        id: "sz",
        symbol: "/s/ · /z/",
        how: "As in English.",
        spelling: "/s/: s, ss, c before e or i, ç, t in -tion. /z/: z, and a single s between two vowels",
        tip: "A single s between vowels is /z/, a double ss is /s/: poison /pwazɔ̃/ (poison) versus poisson /pwasɔ̃/ (fish).",
        examples: [ex("ça", "sa", "that"), ex("rose", "ʁoz", "pink"), ex("zéro", "zeʁo", "zero")],
      },
      {
        id: "sh",
        symbol: "/ʃ/",
        how: "Like \"sh\" in \"ship\", with the lips pushed forward a little.",
        spelling: "ch",
        examples: [ex("chat", "ʃa", "cat"), ex("chose", "ʃoz", "thing"), ex("riche", "ʁiʃ", "rich")],
      },
      {
        id: "zh",
        symbol: "/ʒ/",
        how: "Like the \"s\" in \"measure\" or the \"g\" in \"beige\".",
        spelling: "j; g before e, i",
        examples: [ex("je", "ʒə", "I"), ex("jour", "ʒuʁ", "day"), ex("âge", "ɑʒ", "age")],
      },
      {
        id: "mn",
        symbol: "/m/ · /n/",
        how: "As in English, but /n/ touches the back of the upper teeth with the tip of the tongue.",
        spelling: "m; n",
        examples: [ex("maman", "mamɑ̃", "mum"), ex("nous", "nu", "we"), ex("non", "nɔ̃", "no")],
      },
      {
        id: "ny",
        symbol: "/ɲ/",
        how: "One single sound, like the \"ny\" in \"canyon\". The middle of the tongue presses against the palate.",
        spelling: "gn",
        examples: [ex("montagne", "mɔ̃taɲ", "mountain"), ex("signe", "siɲ", "sign"), ex("agneau", "aɲo", "lamb")],
      },
      {
        id: "l",
        symbol: "/l/",
        how: "Always \"light\": the tip of the tongue touches the back of the upper teeth. Never the dark English \"l\" of \"ball\".",
        spelling: "l, ll",
        examples: [ex("lune", "lyn", "moon"), ex("belle", "bɛl", "beautiful"), ex("il", "il", "he")],
      },
      {
        id: "r",
        symbol: "/ʁ/",
        how: "Made at the back of the throat. Keep the tip of the tongue down behind the lower teeth and raise the back of the tongue towards the soft palate, as if starting a light gargle. It is not rolled, and it is not the English \"r\".",
        spelling: "r, rr",
        tip: "A final r is pronounced (parler, sœur), unlike the -er ending of verbs, which is just /e/.",
        examples: [ex("rouge", "ʁuʒ", "red"), ex("merci", "mɛʁsi", "thank you"), ex("sœur", "sœʁ", "sister")],
      },
    ],
  },
  {
    id: "linking",
    title: "Linking and rhythm",
    intro:
      "French is spoken in rhythm groups, which is why Paulou splits a sentence into chunks. Inside a group, words flow into each other.",
    sounds: [
      {
        id: "silent",
        symbol: "Silent letters",
        how: "Most final consonants are not pronounced. The exceptions are often c, r, f and l.",
        examples: [
          ex("petit", "pəti", "small"),
          ex("grand", "gʁɑ̃", "big"),
          ex("vous", "vu", "you"),
          ex("sac", "sak", "bag"),
          ex("bonjour", "bɔ̃ʒuʁ", "hello"),
        ],
      },
      {
        id: "liaison",
        symbol: "Liaison",
        how: "A silent final consonant is pronounced when the next word begins with a vowel sound, and it attaches to that word. s, x and z sound /z/; d sounds /t/. Paulou treats such a pair as one unit.",
        tip: "Liaison is required in some places (article and noun: les amis), forbidden in others (after \"et\"; before a so-called aspirated h: les héros /le eʁo/) and optional elsewhere.",
        examples: [
          ex("les amis", "le.z‿a.mi", "the friends"),
          ex("un ami", "œ̃.n‿a.mi", "a friend"),
          ex("vous avez", "vu.z‿a.ve", "you have"),
          ex("grand homme", "gʁɑ̃.t‿ɔm", "great man"),
        ],
      },
      {
        id: "enchainement",
        symbol: "Enchaînement",
        how: "A consonant that is always pronounced moves onto the next word when it starts with a vowel. Nothing is added: the syllable boundary just slides.",
        examples: [ex("il a", "i.la", "he has"), ex("une amie", "y.na.mi", "a friend (f.)"), ex("elle est", "ɛ.lɛ", "she is")],
      },
      {
        id: "elision",
        symbol: "Elision",
        how: "Short words ending in a vowel drop it before a vowel sound, written with an apostrophe. The two words are pronounced as one.",
        examples: [ex("l'ami", "la.mi", "the friend"), ex("j'ai", "ʒe", "I have"), ex("c'est", "sɛ", "it is"), ex("qu'il", "kil", "that he")],
      },
      {
        id: "rhythm",
        symbol: "Rhythm",
        how: "French words have no stress of their own. Syllables are about the same length, and the last syllable of a rhythm group is the one that is longer and carries the rise or fall in pitch.",
        tip: "Practise a chunk as one flowing phrase, not as separate words.",
        examples: [],
      },
    ],
  },
];
