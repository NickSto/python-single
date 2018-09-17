#!/usr/bin/env python3
import argparse
import logging
import sys
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Read a log of SMART data and print changing values as series, with one column per
statistic, and one line per timepoint."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('smartlog', nargs='?', type=argparse.FileType('r'), default=sys.stdin,
    help='Log file output by smart-format.py. Default: stdin.')
  parser.add_argument('-s', '--spaces', type=int, default=2,
    help='Number of spaces between columns. Default: %(default)s.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
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

  spacer = ' ' * args.spaces

  data, smartkeys, changed = read_log(args.smartlog)

  smartids_list = sorted(list(changed))

  widths = print_header(smartids_list, smartkeys, spacer)
  print_data(data, smartids_list, widths, spacer)


def read_log(log):
  smartkeys = {}
  last_values = {}
  changed = set()
  data = []
  last_timestamp = None
  for line in log:
    fields = line.rstrip('\r\n').split('\t')
    timestamp = int(fields[0])
    smartid = int(fields[1])
    smartkey = fields[2]
    value = int(fields[3])
    if smartid in last_values and value != last_values[smartid]:
      changed.add(smartid)
    last_values[smartid] = value
    smartkeys[smartid] = smartkey
    if timestamp != last_timestamp:
      data.append({'timestamp':timestamp})
    data[-1][smartid] = value
    last_timestamp = timestamp
  return data, smartkeys, changed


def print_header(smartids_list, smartkeys, spacer):
  line1 = []
  line2 = []
  widths = {}
  for smartid in smartids_list:
    smartkey_abbrev = smartkeys[smartid].replace('_', '').replace('-', '')
    width = len(smartkey_abbrev)
    widths[smartid] = width
    line1.append(str(smartid).rjust(width))
    line2.append(smartkey_abbrev)
  print(*line1, sep=spacer)
  print(*line2, sep=spacer)
  return widths


def print_data(data, smartids_list, widths, spacer):
  for timepoint in data:
    line = []
    for smartid in smartids_list:
      value = timepoint[smartid]
      width = widths[smartid]
      line.append(str(value).rjust(width))
    print(*line, sep=spacer)


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
