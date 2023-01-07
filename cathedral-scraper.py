#!/usr/bin/env python3
import argparse
import logging
import pathlib
import subprocess
import sys
import tempfile
import typing
import bs4
import requests
import yaml

# GET https://cathedral.org/calendar/?filters[modality]=in-person&filters[date]=&filters[types][0]=sightseeing-tours&query=&current_page=2

DOMAIN = 'cathedral.org'
CALENDAR_PATH = '/calendar/'
USER_AGENT = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:108.0.1) Gecko/20100101 Firefox/108.0.1'
ZENITY_CMD = [
  'zenity', '--list', '--title', 'National Cathedral Events', '--width', '750', '--height', '300',
  '--print-column', '4', '--editable', '--column', 'Date', '--column', 'Time', '--column', 'Event',
  '--column', 'URL',
]
ZENITY_ERROR_CMD = [
  'zenity', '--error', '--no-markup', '--width', '400', '--title', 'Cathedral Scraper error',
  '--text'
]
HTML_FIELDS = {
  'date': {'tag':'span', 'class':'event_list_row_time_date', 'critical':True},
  'day': {'tag':'span', 'class':'event_list_row_time_day'},
  'title': {'tag':'span', 'class':'event_list_item_title_link_label', 'critical':True},
  'url': {'tag':'a', 'class':'event_list_item_title_link', 'attr':'href'},
  'time': {'tag':'span', 'class':'event_list_item_time_label_date_item'},
  'location': {'tag':'span', 'class':'event_list_item_detail_label'},
  'tickets': {'tag':'span', 'class':'event_list_item_tickets_link_label'}
}
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_FILTER_FILE = SCRIPT_DIR / 'cathedral-filters.yml'
SILENCE_FILE = pathlib.Path('~/.local/share/nbsdata/SILENCE').expanduser()
DESCRIPTION = """Check upcoming events at the National Cathedral and show ones that might be a
tower climb."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('pages', type=int, nargs='?', default=8,
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
  try:
    get_and_display_events(args.pages, headers, ignore, seen)
  except RuntimeError as error:
    cmd = ZENITY_ERROR_CMD + [str(error)]
    subprocess.run(cmd, check=True)


def get_and_display_events(pages, headers, ignore, seen):
  with tempfile.NamedTemporaryFile(mode='w+t', prefix='cathedral.', suffix='.txt') as tmpfile:
    results = 0
    for event in get_events(f'https://{DOMAIN}{CALENDAR_PATH}', headers, pages):
      logging.info(f'Found event on {event.date}: {event.title}')
      if event.title in ignore:
        logging.info('  in ignore list')
        continue
      if (event.title, event.date) in seen:
        logging.info('  in seen list')
        continue
      results += 1
      print(event.date, event.time, event.title, event.url, sep='\n', file=tmpfile)
    # If we found results, display them in a dialog.
    if results > 0:
      tmpfile.seek(0)
      subprocess.run(ZENITY_CMD, stdin=tmpfile, check=True)


class Event(typing.NamedTuple):
  date: str
  day: str
  title: str
  url: str
  time: str
  location: str
  tickets: str


def get_events(url, headers, pages):
  for page in range(1, pages+1):
    params = {
      'filters[modality]': 'in-person',
      'filters[date]': '',
      'filters[types][0]': 'sightseeing-tours',
      'query': '',
      'current_page': str(page)
    }
    logging.info(f'Requesting page {page}')
    response = requests.post(url, headers=headers, params=params)
    if response.status_code != 200:
      raise RuntimeError(f'Received response code {response.status_code} {response.reason} on page {page}')
    html_bytes = response.content
    soup = bs4.BeautifulSoup(html_bytes, 'html.parser')
    for day_elem in soup.find_all('div', class_='event_list_row'):
      date = find_child_text(day_elem, HTML_FIELDS['date'])
      day = find_child_text(day_elem, HTML_FIELDS['day'])
      for event_elem in day_elem.find_all('li', class_='event_list_item'):
        data = {'date':date, 'day':day}
        for field in Event._fields:
          if field not in data:
            data[field] = find_child_text(event_elem, HTML_FIELDS[field])
        yield Event(**data)


def find_child_text(parent, spec):
  child = parent.find(spec['tag'], class_=spec['class'])
  if spec.get('attr'):
    raw_text = child.attrs[spec['attr']]
  else:
    raw_text = child.text
  if raw_text is None:
    parent_desc = parent.name
    class_ = parent.attrs.get("class")
    if class_:
      parent_desc += '.'+class_
    message = f'Problem searching for child of {parent_desc} with spec {spec}'
    if spec.get('critical'):
      raise RuntimeError(message)
    else:
      logging.warning(message)
  return raw_text.strip()


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
