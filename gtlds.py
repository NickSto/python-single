#!/usr/bin/env python3
import argparse
import logging
import sys
import bs4
assert sys.version_info.major >= 3, 'Python 3 required'

ICANN_URL = 'https://newgtlds.icann.org/en/program-status/delegated-strings'
DESCRIPTION = "Parse the official ICANN list of new gTLDs from "+ICANN_URL+""" and print as a simple
list, one per line."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('input', type=argparse.FileType('r'), default=sys.stdin,
    metavar='delegated-strings.html',
    help='')
  parser.add_argument('-i', '--idn', action='store_true',
    help='Give the IDN-encoded ASCII equivalent of internationalized domains.')
  parser.add_argument('-l', '--lower', action='store_true',
    help='Convert TLDs to lowercase.')
  parser.add_argument('-L', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  soup = bs4.BeautifulSoup(args.input, features='html5lib')

  for tld in parse_tlds_from_soup(soup, idn=args.idn):
    if args.lower:
      print(tld.lower())
    else:
      print(tld)


def parse_tlds_from_soup(soup, idn=False):
  elements = soup.select('#content article.node-16971 > div.field-type-text-with-summary > '
                         'div.field-items > div.field-item.even > table > tbody')
  if len(elements) != 1:
    logging.error('Error: HTML structure not as expected.')
    return False
  table = elements[0]
  for row in table.children:
    if not (isinstance(row, bs4.element.Tag) and row.name == 'tr'):
      continue
    cells = [cell for cell in row.children if isinstance(cell, bs4.element.Tag) and cell.name == 'td']
    if len(cells) != 2:
      continue
    tld = parse_tld_cell(cells[1], idn=idn)
    if tld is not None:
      yield tld


def parse_tld_cell(cell, idn=False):
  children = list(cell.children)
  if len(children) == 1:
    return parse_tld_string(cell.string, idn=idn)
  elif cell.string is None:
    if len(children) == 2 and children[0].name == 'span' and children[0].attrs['dir'] == 'rtl':
      fields = children[1].string.split()
      if len(fields) != 5:
        logging.warning('Warning: Unexpected TLD element structure (issue 1): {}'.format(cell))
        return None
      elif not fields[0].startswith('(xn--'):
        logging.warning('Warning: Unexpected TLD element structure (issue 2): {}'.format(cell))
        return None
      elif not fields[0].endswith(')'):
        logging.warning('Warning: Unexpected TLD element structure (issue 3): {}'.format(cell))
        return None
      logging.info('Info: Child element found inside TLD element: {}'.format(cell))
      if idn:
        return fields[0][1:-1]
      else:
        return children[0].string
    else:
      logging.warning('Warning: Unexpected TLD element structure (issue 4): {}'.format(cell))
      return None
  else:
    logging.warning('Warning: Unexpected TLD element structure (issue 5): {}'.format(cell))
    return None


def parse_tld_string(tld_raw, idn=False):
  fields = tld_raw.split()
  if len(fields) == 0:
    logging.warning('Warning: Empty TLD field {!r}.'.format(tld_raw))
    return None
  if len(fields) == 1:
    if fields[0].startswith('xn--'):
      logging.warning('Warning: Unrecognized TLD field {!r} (issue 1).'.format(tld_raw))
      return None
    else:
      return fields[0]
  elif len(fields) > 1:
    if fields[0].startswith('xn--') and fields[1].startswith('('):
      if fields[1].endswith(',') or fields[1].endswith(')'):
        if idn:
          return fields[0]
        else:
          return fields[1][1:-1]
      else:
        logging.warning('Warning: Unrecognized TLD field {!r} (issue 2).'.format(tld_raw))
    elif fields[1].startswith('(xn') and fields[1].endswith(')'):
      if fields[1].startswith('(xn―'):
        logging.info('Info: Correcting typo ("--" replaced by horizontal bar): '
                     '{!r}'.format(tld_raw))
      elif not fields[1].startswith('(xn--'):
        logging.warning('Warning: Unrecognized TLD field {!r} (issue 3).'.format(tld_raw))
        return None
      if idn:
        return fields[1][1:-1].replace('―', '--')
      else:
        return fields[0]
    elif fields[1] == '–' and fields[0].endswith(')') and '(xn--' in fields[0]:
      subfields = fields[0].split('(xn--')
      if len(subfields) != 2:
        logging.warning('Warning: Unrecognized TLD field {!r} (issue 4).'.format(tld_raw))
        return None
      logging.info('Info: Correcting typo (missing space between domain and IDN parenthetical): '
                   '{!r}'.format(tld_raw))
      if idn:
        return 'xn--'+subfields[1][:-1]
      else:
        return subfields[0]
    else:
      logging.warning('Warning: Unrecognized TLD field {!r} (issue 5).'.format(tld_raw))
      return None


def fail(message):
  logging.critical(message)
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
