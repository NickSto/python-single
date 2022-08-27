#!/usr/bin/env python3
import argparse
import logging
import pathlib
import subprocess
import sys
import tempfile
import requests

DOMAIN = 'cathedral.org'
CALENDAR_PATH = '/wp-admin/admin-ajax.php'
USER_AGENT = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:103.0) Gecko/20100101 Firefox/103.0'
FILTER = {
  'Online Morning Prayer', 'Weekday Choral Evensong', 'Carillon Recital', 'Holy Eucharist',
  'Sunday Choral Evensong', 'Behind the Scenes Tour', 'Sightseeing Admission',
  'Sanctuary Ministry Meeting', 'Racial Justice Task Force Meeting',
  'Martha&#8217;s Table Ministry', 'Reimagining the Oberammergau Passion Play after the Holocaust',
}
SEEN = {
  ('Thursday, September 8, 2022', 'Bell Tower Climb'),
  ('Saturday, September 17, 2022', 'Angels and Monsters Tower Climb'),
}
ZENITY_CMD = [
  'zenity', '--list', '--title', 'National Cathedral Events', '--width', '750', '--height', '300',
  '--print-column', '2', '--editable', '--column', 'Date', '--column', 'Event'
]
SILENCE_FILE = pathlib.Path('~/.local/share/nbsdata/SILENCE').expanduser()
DESCRIPTION = """Check upcoming events at the National Cathedral and show ones that might be a
tower climb."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('pages', type=int, nargs='?', default=5,
    help='How many pages of events to request. 5 is usually enough to get about a month of '
      'results. Default: %(default)s')
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

  headers = {'user-agent':USER_AGENT}

  with tempfile.NamedTemporaryFile(mode='w+t', prefix='cathedral.', suffix='.txt') as tmpfile:
    results = 0
    for date, title in get_events(f'https://{DOMAIN}{CALENDAR_PATH}', headers, args.pages):
      if title not in FILTER and (date, title) not in SEEN:
        results += 1
        print(date, file=tmpfile)
        print(title, file=tmpfile)
    # If we found results, display them in a dialog.
    if results > 0:
      tmpfile.seek(0)
      subprocess.run(ZENITY_CMD, stdin=tmpfile, check=True)


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
        title = event['event_title']
        yield date, title


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
