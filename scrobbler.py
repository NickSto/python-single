#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys
import time

DEFAULT_LOG = pathlib.Path('~/aa/computer/logs/scrobbles.tsv').expanduser()
DEFAULT_ERROR_LOG = pathlib.Path('~/.local/share/nbsdata/stderr.log').expanduser()
DESCRIPTION = """Small script to let Audacious log played songs to a file."""
USAGE='$ %(prog)s state artist track_title album length mp3_path'
EPILOG = """In Audacious' Song Change plugin: 'scrobbler.py start "%a" "%T" "%b" "%l" "%f"'"""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, usage=USAGE, description=DESCRIPTION, epilog=EPILOG)
  options = parser.add_argument_group('Options')
  options.add_argument('state', choices=('start', 'end'),
    help='Whether this was called at the start or end of the song.')
  options.add_argument('artist')
  options.add_argument('title',
    help='The song title.')
  options.add_argument('album')
  options.add_argument('length', type=lambda len: round(int(len)/1000),
    help='The length of the song, in milliseconds.')
  options.add_argument('path',
    help="Path to the song file. Prepended with the protocol (like 'file:' or 'http:') and "
      'percent-encoded.')
  options.add_argument('-o', '--output', type=pathlib.Path, default=DEFAULT_LOG,
    help='File to log the event to. Default: %(default)s')
  options.add_argument('-h', '--help', action='help',
    help='Print this argument help text and exit.')
  logs = parser.add_argument_group('Logging')
  logs.add_argument('-l', '--log', type=pathlib.Path, default=DEFAULT_ERROR_LOG,
    help='Append error messages to this file. Default: %(default)s')
  volume = logs.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  error_log = args.log.open('a')
  logging.basicConfig(stream=error_log, level=args.volume, format='%(message)s')

  now = round(time.time())

  with args.output.open('a') as log_file:
    print(
      now, args.state, args.artist, args.title, args.album, args.length, args.path,
      sep='\t', file=log_file
    )


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
