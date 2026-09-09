# Japanese Sentences to Anki Decks

Turn your i+1 Japanese sentences into an Anki deck with VOICEVOX audio.

All you have to do is bring a .json file of sentences
(see [Input Format](#input-format) for instructions) and run the script.

The script will then synthesise the audio locally
with [VOICEVOX](https://voicevox.hiroshiba.jp/), highlights the target word in
each sentence, and writes a ready-to-import `.apkg`.

Nothing is uploaded anywhere and no API keys are involved — VOICEVOX runs on
your own machine.

The idea behind the format is **i+1**: every sentence contains exactly one word
you don't know yet. The script doesn't check that for you. It assumes your
sentences are already built that way, but the card layout is designed around
it, which is why the new word gets its own emphasis and its own audio.

## Features

Each sentence becomes one note with:

- the sentence, with the **target word highlighted in dark green**
- kana reading, translation, and the new word with its own reading and meaning
- audio for the sentence, and for the target word on its own
- optionally an audio-first card instead of, or in addition to, the reading card

## Requirements

- Python 3.8+
- `pip install -r requirements.txt`
- [VOICEVOX](https://voicevox.hiroshiba.jp/) installed and running
- `ffmpeg` — optional but recommended; without it decks are built with WAV
  files and end up roughly ten times larger

## Usage

Start the VOICEVOX **engine** by simply running the program in the background.
The script will then be able to talk to an HTTP server on `127.0.0.1:50021`.

> Use --host and --port if your engine listens somewhere else.

If you don't already know which **style ID** you want to use, run

```bash
# list the available voices and their style IDs
python build_anki_deck.py --list-speakers
```

> you may need to change your terminal font in order to see the character names

After that use the **style ID**, your **.json** and run

```bash
# build a deck
python build_anki_deck.py -i example.json -s 13

# slower audio, and both card types
python build_anki_deck.py -i example.json -s 13 --speed 0.8 --card-type both
```

Next you want to import your newly generated deck in Anki via *File → Import*

## Options

| Option | Effect |
| ------ | ------ |
| `-i, --input` | input JSON |
| `-o, --output` | output file (default `japanese_sentences.apkg`) |
| `-d, --deck` | deck name, overrides `deck` from the JSON |
| `-s, --speaker` | style ID from `--list-speakers` (default: 13) |
| `--speed` | speaking rate, e.g. `0.8` for slower audio (default: 1.0) |
| `--pause` | stretch the pauses inside the sentence (e.g: 1.3) |
| `--no-word-audio` | skip the separate audio for the target word |
| `--card-type {reading,audio,both}` | which cards to create per sentence (default: `reading`) |
| `--media-dir` | where the audio files are cached (default `media/`) |
| `--no-mp3` | keep WAV instead of converting to MP3 |
| `--no-audio` | build the deck without any audio |
| `--host`, `--port` | address of the VOICEVOX engine |
| `--list-speakers` | print the available voices and exit |

> `-s` takes a **style ID**, not a character number: every character has several
speaking styles (normal, cheerful, sad), each with its own ID. `--list-speakers`
prints them. A calm default style works best for study sentences.

### Card types

- **`reading`** — sentence on the front, translation and target word on the back
- **`audio`** — audio on the front, sentence and translation on the back
- **`both`** — both of the above, so every sentence turns into two cards

`both` doubles your daily reviews, so it's worth deciding this before you build
a large deck: switching later means Anki treats it as a different note type.

## Input format

See `example.json`:

```json
{
  "deck": "i+1 Sentences",
  "cards": [
    {
      "sentence": "電車が遅れましたから、会社に電話しました。",
      "reading": "でんしゃがおくれましたから、かいしゃにでんわしました。",
      "translation": "The train was late, so I called the office.",
      "new_word": {
        "word": "遅れる",
        "reading": "おくれる",
        "definition": "to be late, to be delayed",
        "sentence_form": "遅れました"
      },
      "hint": ""
    }
  ]
}
```

> AI may help you format and fill in missing information for your sentences.

| Field | Meaning |
| ----- | ------- |
| `sentence` | the sentence — the only required field |
| `reading` | the full sentence in kana |
| `translation` | translation of the sentence |
| `new_word.word` | the target word in **dictionary form** |
| `new_word.reading` | its reading in kana |
| `new_word.definition` | whats the meaning of the word |
| `new_word.sentence_form` | the word **exactly as it appears in the sentence** |
| `hint` | optional note, e.g. a grammar remark |

> `deck` sets the deck name, `::` creates subdecks,
and `-d` on the command line overrides it.

### About `sentence_form`

Verbs and adjectives are listed in dictionary form but appear conjugated in the
sentence — 遅れる vs. 遅れました. `sentence_form` tells the script which substring
to highlight, and must match the sentence character for character.

If you leave it out, the script falls back to searching for the word itself and
then for progressively shorter stems, so 遅れる still finds 遅れ inside 遅れました
— just without the ました. Anything it can't locate at all is listed by name
when the run finishes; those cards are still built, only without highlighting.

## Notes

**Rebuilding is safe.** The note GUID is derived from the sentence text, so
re-importing an updated deck updates the existing cards instead of creating
duplicates — your review history survives. Append new sentences to your JSON
and build again.

**Audio is cached.** File names are a hash of sentence, speaker and speed, so a
second run only synthesises what's new. Delete `media/` when you switch voices,
otherwise old files just linger. Both `media/` and `*.apkg` are in
`.gitignore`.

**Word audio comes from the kana reading.** For the isolated target word the
script speaks `new_word.reading` rather than the kanji spelling — single words
without sentence context get misread noticeably more often. If no reading is
given, the word itself is synthesised.

**Wrong readings in a sentence.** VOICEVOX occasionally misreads homographs
like 行った or 一日. The quickest fix for a single sentence is to load it in the
VOICEVOX editor, correct the reading by hand, export a WAV and replace the file
in `media/` under the same name.

**Colours** are set in the `CSS` block in the script, under `.target`
and `.new .w` (the word on the back). Both switch
to a lighter green in Anki's night mode.

## VOICEVOX terms of use

VOICEVOX itself is not part of this repository — you install it separately.
This project only sends text to its local API.

The audio you generate is a different matter. Each voice character has its own
terms, and crediting is mandatory for practically all of them, in the format
`VOICEVOX:CharacterName`. That applies when you publish or share generated
audio — a deck you keep to yourself is fine. Check the terms for the character
you use on the [official site](https://voicevox.hiroshiba.jp/) before sharing a
deck built with this script.

## License

MIT
