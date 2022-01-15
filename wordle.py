#!/usr/bin/env python3
import argparse
import logging
import pathlib
import string
import sys

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_WORDLIST = pathlib.Path('~/aa/misc/ghent-word-list.tsv').expanduser()
DEFAULT_FREQ_LIST = SCRIPT_DIR/'wordle-freqs.tsv'
DESCRIPTION = """How much can a simple script help solve wordles?
This gives a list of the possible words that fit what you currently know based on your previous
guesses. Thus it can't tell you what to guess first. But based on the letter frequency of 5 letter
words, ATONE is the best I've found."""
EPILOG = 'Wordle: https://www.powerlanguage.co.uk/wordle/'


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION, epilog=EPILOG)
  options = parser.add_argument_group('Options')
  options.add_argument('fixed',
    help='The letters with known locations. Give dots for unknowns.')
  options.add_argument('present',
    help='The known letters without a known location.')
  options.add_argument('absent',
    help='The letters known to be absent. Repeat letters are fine. It can also handle letters '
      "present in the 'fixed' argument (they're ignored).")
  options.add_argument('-w', '--word-list', type=argparse.FileType('r'),
    default=DEFAULT_WORDLIST.open(),
    help=f'Word list to use. Default: {str(DEFAULT_WORDLIST)}')
  options.add_argument('-f', '--letter-freqs', type=argparse.FileType('r'),
    default=DEFAULT_FREQ_LIST.open(),
    help='File containing the frequencies of letters in all --word-length words.')
  options.add_argument('-L', '--word-length', default=5)
  options.add_argument('-h', '--help', action='help',
    help='Print this argument help text and exit.')
  logs = parser.add_argument_group('Logging')
  logs.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = logs.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  fixed = parse_fixed(args.fixed)
  present = set(args.present.lower())
  absent = parse_absent(args.absent, fixed)

  words = read_wordlist(args.word_list, args.word_length)
  logging.info(f'Read {len(words)} {args.word_length} letter words.')
  freqs = read_letter_freqs(args.letter_freqs)

  candidates = []
  for word in words:
    candidate = True
    for letter, place in fixed.items():
      if word[place-1] != letter:
        candidate = False
    for letter in present:
      if letter not in word:
        candidate = False
    for letter in absent:
      if letter in word:
        candidate = False
    if candidate:
      candidates.append(word)

  candidates.sort(key=lambda word: score_word(word, freqs), reverse=True)
  print('\n'.join(candidates))


def parse_fixed(fixed_str):
  fixed = {}
  for place, letter in enumerate(fixed_str,1):
    if letter == '.':
      continue
    fixed[letter.lower()] = place
  return fixed


def parse_absent(absent_str, fixed):
  absent = set()
  for letter in absent_str.lower():
    if letter not in fixed:
      absent.add(letter)
  return absent


def score_word(word, freqs):
  score = 0
  seen = set()
  repeats = 0
  for letter in word:
    if letter in seen:
      repeats += 1
    seen.add(letter)
    score += freqs[letter]
  return score / (10**repeats)


def read_wordlist(word_file, wordlen=5):
  words = set()
  for line_raw in word_file:
    fields = line_raw.rstrip('\r\n').split()
    if not fields or fields[0].startswith('#'):
      continue
    word = fields[0].lower()
    if len(word) != wordlen:
      continue
    invalid = False
    for letter in word:
      if letter not in string.ascii_lowercase:
        invalid = True
    if invalid:
      continue
    words.add(word)
  return words


def read_letter_freqs(freqs_file):
  freqs = {}
  for line_raw in freqs_file:
    fields = line_raw.rstrip('\r\n').split()
    if len(fields) < 2 or fields[0].startswith('#'):
      continue
    letter = fields[0]
    count = int(fields[1])
    freqs[letter] = count
  return freqs


def fail(message):
  logging.critical(f'Error: {message}')
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception(message)


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
