"""
Builds an Anki-Deck with VOICEVOX audio from an .json file.
See README.md for further information.
"""

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys

try:
    import genanki
    import requests
except ImportError as err:
    sys.exit(
        f"Missing dependency ({err.name}). Install with:  pip install requests genanki"
    )

# Fixed IDs used for re-importing updates instead of creating duplicates
MODEL_ID = 1607392930
DECK_ID = 2059400115

KANA = re.compile(r"[ぁ-んァ-ヴー]")

############################
# JSON Input
############################


def parse_input(path):
    """Read the JSON file and normalise it"""
    try:
        with open(path, encoding="utf-8") as file:
            raw = json.load(file)
    except json.JSONDecodeError as err:
        sys.exit(f"{path} is not valid JSON: {err}\n")

    if not isinstance(raw, dict):
        sys.exit(f'{path}: expected a JSON object with a "cards" key.')

    deck_name = raw.get("deck")
    items = raw.get("cards")
    if items is None:
        sys.exit('The JSON has no "cards" key.')

    cards = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("sentence"):
            print(f' Skipped entry {index}: no "sentence"')
            continue

        new_word = item.get("new_word") or {}
        if not isinstance(new_word, dict):
            sys.exit(f'Card {index}: "new_word" must be an object, not a string.')

        cards.append(
            {
                "sentence": str(item["sentence"]).strip(),
                "reading": str(item.get("reading", "")).strip(),
                "translation": str(item.get("translation", "")).strip(),
                "word": str(new_word.get("word", "")).strip(),
                "word_reading": str(new_word.get("reading", "")).strip(),
                "word_def": str(new_word.get("definition", "")).strip(),
                "word_form": str(new_word.get("sentence_form", "")).strip(),
                "hint": str(item.get("hint", "")).strip(),
            }
        )
    if not cards:
        sys.exit("No usable cards in the input file.")

    return cards, deck_name


def highlight(sentence, word, form=""):
    """Wrap the target word in <span class="target">

    Verbs and adjectives appear conjugated in the sentence, so the stem is
    used as a fallback: 遅れる -> 遅れ  matches 遅れました.
    """

    sentence_html = html.escape(sentence, quote=False)
    possible_target_words = []
    if form:
        possible_target_words.append(form)
    if word:
        possible_target_words.append(word)
        stem = word
        while len(stem) > 2 and KANA.match(stem[-1]):
            stem = stem[:-1]
            possible_target_words.append(stem)

    for candidate in possible_target_words:
        candidate_html = html.escape(candidate, quote=False)
        if candidate_html and candidate_html in sentence_html:
            return sentence_html.replace(
                candidate_html, f'<span class="target">{candidate_html}</span>', 1
            ), True

    return sentence_html, not bool(word)


############################
# VOICEVOX
############################


class Voicevox:
    def __init__(self, host="127.0.0.1", port=50021, speaker=13, timeout=90):
        self.base = f"http://{host}:{port}"
        self.speaker = speaker
        self.timeout = timeout

    def check(self):
        try:
            voicevox = requests.get(self.base + "/version", timeout=5).text.strip(
                '"\n '
            )
        except requests.exceptions.RequestException:
            sys.exit(
                f"Cannot reach VOICEVOX at {self.base}.\nStart VOICEVOX and try again."
            )

        print(f"VOICEVOX engine {voicevox} is up.")

        try:
            requests.post(
                self.base + "/initialize_speaker",
                params={"speaker": self.speaker},
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException:
            pass

    def speakers(self):
        return requests.get(self.base + "/speakers", timeout=10).json()

    def synth(self, text, speed=1.0, pause_scale=1.0):
        """Text -> WAV bytes in two steps: fetch the query, then adjust it."""
        audio_query = requests.post(
            self.base + "/audio_query",
            params={"text": text, "speaker": self.speaker},
            timeout=self.timeout,
        )
        audio_query.raise_for_status()
        query = audio_query.json()
        query["pauseLengthScale"] = pause_scale
        query["prePhonemeLength"] = 0.1  # a little silence at both ends,
        query["postPhonemeLength"] = 0.3  # otherwise it sounds clipped
        query["speedScale"] = speed

        audio_response = requests.post(
            self.base + "/synthesis",
            params={"speaker": self.speaker},
            headers={"Content-Type": "application/json"},
            data=json.dumps(query).encode("utf-8"),
            timeout=self.timeout,
        )
        audio_response.raise_for_status()
        return audio_response.content


############################
# Audio
############################


def have_ffmpeg():
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def to_mp3(wav_path, mp3_path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            wav_path,
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "5",
            mp3_path,
        ],
        check=True,
    )
    os.remove(wav_path)


def audio_name(text, speaker, speed, prefix):
    """Generate a deterministic audio filename from the text, speaker, and speed."""

    h = hashlib.sha1((f"{text}|{speaker}|{speed}").encode("utf-8"))
    return f"{prefix}_{h.hexdigest()[:12]}"


############################
# Anki
############################


CSS = """
.card { font-family: "Hiragino Sans", "Yu Gothic", "Noto Sans JP", sans-serif;
        font-size: 20px; text-align: center; line-height: 1.7; }
.jp { font-size: 34px; line-height: 1.5; }
.kana { font-size: 18px; opacity: .6; margin-top: 6px; }
.translation { font-size: 20px; margin-top: 14px; }
.target { color: #1f6b3a; }
.nightMode .target, .night_mode .target { color: #7fd39b; }
.new { margin-top: 20px; font-size: 22px; }
.new .w { color: #1f6b3a; font-size: 26px; }
.nightMode .new .w, .night_mode .new .w { color: #7fd39b; }
.new .r { font-size: 17px; opacity: .6; }
.hint { margin-top: 14px; font-size: 15px; opacity: .6; }
hr#answer { border: none; border-top: 1px solid rgba(128,128,128,.35);
            margin: 22px 0 4px; }
"""

FIELDS = [
    "Sentence",
    "Reading",
    "Translation",
    "NewWord",
    "WordReading",
    "WordDefinition",
    "Hint",
    "Audio",
    "AudioWord",
]

NEW_WORD_BLOCK = """{{#NewWord}}<div class="new">
  <span class="w">{{NewWord}}</span>
  {{#WordReading}}<span class="r">（{{WordReading}}）</span>{{/WordReading}}
  {{#WordDefinition}}<div>{{WordDefinition}}</div>{{/WordDefinition}}
  {{AudioWord}}
</div>{{/NewWord}}"""

TEMPLATE_READING = {
    "name": "Reading",
    "qfmt": '<div class="jp">{{Sentence}}</div>',
    "afmt": """<div class="jp">{{Sentence}}</div>
{{#Reading}}<div class="kana">{{Reading}}</div>{{/Reading}}
<hr id="answer">
<div class="translation">{{Translation}}</div>
"""
    + NEW_WORD_BLOCK
    + """
{{Audio}}{{#Hint}}<div class="hint">{{Hint}}</div>{{/Hint}}
""",
}

TEMPLATE_LISTENING = {
    "name": "Listening",
    "qfmt": '{{#Audio}}{{Audio}}<div class="hint">What do you hear?</div>{{/Audio}}',
    "afmt": """{{FrontSide}}<hr id="answer">
<div class="jp">{{Sentence}}</div>
{{#Reading}}<div class="kana">{{Reading}}</div>{{/Reading}}
<div class="translation">{{Translation}}</div>
"""
    + NEW_WORD_BLOCK
    + """
{{#Hint}}<div class="hint">{{Hint}}</div>{{/Hint}}
""",
}


class Note(genanki.Note):
    @property
    def guid(self):
        # GUID derived from the sentence text only -> re-importing updates
        # existing cards instead of creating duplicates
        return genanki.guid_for(re.sub(r"<[^>]+>", "", self.fields[0]))


############################
# Main run
############################


def main():
    ap = argparse.ArgumentParser(
        description="Build an Anki deck (.apkg) from a JSON sentence list, "
        "with audio from VOICEVOX."
    )
    ap.add_argument("-i", "--input", help="JSON file with the sentences")
    ap.add_argument("-o", "--output", default="japanese_sentences.apkg")
    ap.add_argument(
        "-d",
        "--deck",
        help='deck name (:: creates subdecks); overrides "deck" from the JSON',
    )
    ap.add_argument(
        "-s",
        "--speaker",
        type=int,
        default=13,
        help="style ID from --list-speakers (default: 13)",
    )
    ap.add_argument("--speed", type=float, default=1.0, help="speaking rate")
    ap.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="scale factor for pauses inside the sentence",
    )
    ap.add_argument(
        "--no-word-audio",
        action="store_true",
        help="skip the separate audio for the target word",
    )
    ap.add_argument(
        "--card-type",
        choices=["reading", "audio", "both"],
        default="reading",
        help="which cards to create per sentence (default: reading)",
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=50021)
    ap.add_argument("--media-dir", default="media")
    ap.add_argument("--no-mp3", action="store_true", help="keep WAV files")
    ap.add_argument(
        "--no-audio", action="store_true", help="build the deck without any audio"
    )
    ap.add_argument("--list-speakers", action="store_true")
    args = ap.parse_args()

    voicevox = Voicevox(args.host, args.port, args.speaker)

    if args.card_type != "reading" and args.no_audio:
        ap.error(
            "Cannot create audio cards without audio. Please change some arguments."
        )

    if args.list_speakers:
        voicevox.check()
        for speaker in voicevox.speakers():
            styles = ", ".join(f"{st['name']}={st['id']}" for st in speaker["styles"])
            print(f"{speaker['name']:<22} {styles}")
        return

    if not args.input:
        ap.error("--input is missing (or use --list-speakers)")

    cards, deck_name_from_json = parse_input(args.input)
    deck_name = args.deck or deck_name_from_json or "i+1 Sentences"
    print(f"{len(cards)} sentences loaded.")

    use_mp3 = not args.no_mp3 and have_ffmpeg()
    if not args.no_audio:
        voicevox.check()
        if not use_mp3 and not args.no_mp3:
            print(
                "Note: ffmpeg not found - building the deck with WAV files (much larger in size)"
            )
        os.makedirs(args.media_dir, exist_ok=True)

    media, notes, unmatched = [], [], []

    def get_audio(text, rate, prefix):
        """Synthesise (with caching) and return the [sound:...] tag."""

        if args.no_audio or not text or rate is None:
            return ""

        extension = "mp3" if use_mp3 else "wav"
        name = audio_name(text, args.speaker, rate, prefix) + "." + extension
        path = os.path.join(args.media_dir, name)
        if not os.path.exists(path):
            wav = voicevox.synth(text, speed=rate, pause_scale=args.pause)
            wav_path = path[:-4] + ".wav"
            with open(wav_path, "wb") as file:
                file.write(wav)
            if use_mp3:
                to_mp3(wav_path, path)
        media.append(path)
        return f"[sound:{name}]"

    for index, card in enumerate(cards, 1):
        sentence_html, ok = highlight(card["sentence"], card["word"], card["word_form"])
        if not ok:
            unmatched.append((card["word"], card["sentence"]))

        # used for kana reading of the isolated word
        word_text = "" if args.no_word_audio else (card["word_reading"] or card["word"])

        fields = [
            sentence_html,
            html.escape(card["reading"], quote=False),
            html.escape(card["translation"], quote=False),
            html.escape(card["word"], quote=False),
            html.escape(card["word_reading"], quote=False),
            html.escape(card["word_def"], quote=False),
            html.escape(card["hint"], quote=False),
            get_audio(card["sentence"], args.speed, "jp"),
            get_audio(word_text, args.speed, "w"),
        ]
        print(f" [{index}/{len(cards)}] {card['sentence'][:42]}")
        notes.append(fields)

    templates = []
    if args.card_type == "both":
        templates.append(TEMPLATE_READING)
        templates.append(TEMPLATE_LISTENING)
        model_offset = 2
    elif args.card_type == "audio":
        templates.append(TEMPLATE_LISTENING)
        model_offset = 1
    else:
        templates.append(TEMPLATE_READING)
        model_offset = 0

    model = genanki.Model(
        MODEL_ID + model_offset,
        "Japanese i+1 (VOICEVOX)",
        fields=[{"name": field} for field in FIELDS],
        templates=templates,
        css=CSS,
    )

    deck = genanki.Deck(DECK_ID, deck_name)
    for fields in notes:
        deck.add_note(Note(model=model, fields=fields))

    pkg = genanki.Package(deck)
    pkg.media_files = sorted(set(media))
    pkg.write_to_file(args.output)

    if unmatched:
        print("\nNot found in the sentence (no highlight applied):")
        for word, sentence in unmatched:
            print(f" {word} in: {sentence}")
        print(' -> add "sentence_form" to those cards.')

    size = os.path.getsize(args.output) / 1048576
    print(
        f"\nDone: {args.output}  ({len(notes)} notes, {len(set(media))} audio files, {size:.1f} MB)"
    )
    print(f"Deck: {deck_name} - import it in Anki via File -> Import.")


if __name__ == "__main__":
    main()
