#!/usr/bin/env python3
import argparse
import logging
import pathlib
import subprocess
import sys
import tempfile
import typing
import requests
import yaml

DOMAIN = 'cathedral.org'
CALENDAR_PATH = '/wp-admin/admin-ajax.php'
USER_AGENT = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:103.0) Gecko/20100101 Firefox/103.0'
ZENITY_CMD = [
  'zenity', '--list', '--title', 'National Cathedral Events', '--width', '750', '--height', '300',
  '--print-column', '4', '--editable', '--column', 'Date', '--column', 'Time', '--column', 'Event',
  '--column', 'URL',
]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_FILTER_FILE = SCRIPT_DIR / 'cathedral-filters.yml'
SILENCE_FILE = pathlib.Path('~/.local/share/nbsdata/SILENCE').expanduser()
DESCRIPTION = """Check upcoming events at the National Cathedral and show ones that might be a
tower climb."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('pages', type=int, nargs='?', default=5,
    help='How many pages of events to request. 5 is usually enough to get about a month of '
      'results. Default: %(default)s')
  options.add_argument('-f', '--filters', type=pathlib.Path, default=DEFAULT_FILTER_FILE,
    help='File with filters. Default: %(default)s')
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

  with args.filters.open() as filters_file:
    filters = yaml.safe_load(filters_file)
  ignore = set(filters['ignore'])
  seen = {(s['title'], s['date']) for s in filters['seen']}

  if SILENCE_FILE.exists():
    logging.warning(f'Warning: Silence file {str(SILENCE_FILE)} exists. Exiting..')
    return 1

  headers = {'user-agent':USER_AGENT}

  with tempfile.NamedTemporaryFile(mode='w+t', prefix='cathedral.', suffix='.txt') as tmpfile:
    results = 0
    for event in get_events(f'https://{DOMAIN}{CALENDAR_PATH}', headers, args.pages):
      if event.title not in ignore and (event.title, event.date) not in seen:
        results += 1
        print(event.date, event.time, event.title, event.url, sep='\n', file=tmpfile)
    # If we found results, display them in a dialog.
    if results > 0:
      tmpfile.seek(0)
      subprocess.run(ZENITY_CMD, stdin=tmpfile, check=True)


class Event(typing.NamedTuple):
  date: str
  title: str
  url: str
  time: str
  location: str
  tickets: str
  mapping = {
    'title':'event_title', 'url':'event_url', 'time':'event_time', 'location':'event_location',
    'tickets':'tickets_url'
  }


def get_events(url, headers, pages):
  for page in range(1, pages+1):
    data = {
      'action': 'e11_search_calendar_dates',
      'data': f'calendar_list_date=&calendar_empty_list_date=&paged={page}',
      'paged': str(page)
    }
    response = requests.post(url, headers=headers, data=data)
    if response.status_code != 200:
      fail(f'Received response code {response.status_code} {response.reason} on page {page}')
    data = response.json()
    for day in data['results']:
      date = day['date_header']
      for event in day['events']:
        data = {'date':date}
        for attr, field in Event.mapping.items():
          data[attr] = event.get(field)
        yield Event(**data)


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
