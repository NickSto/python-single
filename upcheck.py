#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys
import time
import requests
assert sys.version_info.major >= 3, 'Python 3 required'

NOW = time.time()
NULL_STR = '.'
SILENCE_FILE = pathlib.Path('~/.local/share/nbsdata/SILENCE').expanduser()
DEFAULT_USER_AGENT = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:77.0) Gecko/20100101 Firefox/77.0'
DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('url', type=format_url,
    help='')
  options.add_argument('-u', '--user-agent', default=DEFAULT_USER_AGENT,
    help='Default: %(default)s')
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

  if SILENCE_FILE.exists():
    logging.warning(f'Warning: Silence file {str(SILENCE_FILE)} exists. Exiting..')
    return 1

  try:
    response = requests.get(args.url, headers={'User-Agent':args.user_agent})
  except requests.RequestException as error:
    exception = type(error).__name__
    status = None
    result = 'down'
  else:
    exception = None
    status = response.status_code
    result = 'up'

  print(format_output(int(NOW), result, status, exception))


def format_url(raw_url):
  if raw_url.startswith('http://') or raw_url.startswith('https://'):
    return raw_url
  else:
    return 'http://'+raw_url


def format_output(*fields):
  return '\t'.join([format_field(value) for value in fields])


def format_field(raw_value):
  if raw_value is None:
    return NULL_STR
  else:
    return str(raw_value)


def fail(message):
  logging.critical('Error: '+str(message))
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception(message)


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
