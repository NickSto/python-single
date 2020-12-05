#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import re
import subprocess
import sys
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Read battery stats from upower and format into one line for a log entry."""
SECTION_LINE_RE = r'^  ([^ ].*[^ ]):?$'
INFO_LINE_RE = r'([^ ][^:]*): +([^ ].*)$'
HISTORY_LINE_RE = r'^    (\d{10})\t'
TIME_UNITS = {'seconds':1, 'minutes':60, 'hours':60*60, 'days':24*60*60}
COLUMNS = (
  {'key':('root','updated'), 'type':'timestamp'},
  {'key':('root','native-path'), 'type':str},
  {'key':('battery','state'), 'type':str},
  {'key':('battery','energy'), 'type':'unit', 'args':(' Wh',)},
  {'key':('battery','energy-empty'), 'type':'unit', 'args':(' Wh',)},
  {'key':('battery','energy-full'), 'type':'unit', 'args':(' Wh',)},
  {'key':('battery','energy-rate'), 'type':'unit', 'args':(' W',)},
  {'key':('battery','voltage'), 'type':'unit', 'args':(' V',)},
  {'key':('battery','time to empty'), 'type':'time'},
  {'key':('battery','time to full'), 'type':'time'},
  {'key':('battery','percentage'), 'type':'unit', 'args':('%',)},
  {'key':('battery','capacity'), 'type':'unit', 'args':('%',)},
)

def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('device', nargs='?',
    help='The device to use. If not given, this will auto-discover the battery device.')
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

  if args.device:
    device = args.device
  else:
    device = get_device()
    logging.info(f'Info: Found battery device: {device!r}')

  data = info_to_dict(parse_info(run_command('upower', '--show-info', device)))
  columns = get_output_columns(data)
  print(*columns, sep='\t')


def get_device():
  device = None
  for line in run_command('upower', '--enumerate'):
    base = os.path.basename(line)
    if base.startswith('battery_'):
      if device is None:
        device = line
      else:
        raise RuntimeError(f'Found multiple battery devices: {device!r} and {line!r}')
  return device


def parse_info(lines):
  for line in lines:
    type_, line_section, key, value = parse_line(line)
    if line_section is not None:
      section = line_section
    if type_ in ('heading', 'history'):
      continue
    yield section, key, value


def parse_line(line):
  if match := re.search(r'^  '+INFO_LINE_RE, line):
    type_ = 'metadata'
    section = 'root'
    key = match.group(1)
    value = match.group(2)
  elif match := re.search(SECTION_LINE_RE, line):
    type_ = 'heading'
    section = match.group(1)
    key = None
    value = None
  elif match := re.search(r'^    '+INFO_LINE_RE, line):
    type_ = 'data'
    section = None
    key = match.group(1)
    value = match.group(2)
  elif match := re.search(HISTORY_LINE_RE, line) or line == '':
    type_ = 'history'
    section = None
    key = None
    value = None
  else:
    raise ValueError(f'Unrecognized line: {line!r}')
  return type_, section, key, value


def info_to_dict(data_iter):
  data_dict = {}
  for section, key, value in data_iter:
    data_dict[(section, key)] = value
  return data_dict


def get_output_columns(data):
  output = []
  for column in COLUMNS:
    key = column['key']
    raw_value = data.get(key)
    if raw_value is None:
      value = '.'
    else:
      type_ = column['type']
      if isinstance(type_, type):
        value = type_(raw_value)
      else:
        parser_name = 'parse_'+type_
        parser = globals()[parser_name]
        args = column.get('args', ())
        value = parser(raw_value, *args)
    output.append(value)
  return output


def parse_unit(unit_str, unit):
  if unit_str.endswith(unit):
    return unit_str[:-len(unit)]
  else:
    raise ValueError(f'Invalid unit string: {unit_str!r} does not end with {unit!r}')


def parse_time(time_str):
  """Parse an amount of time like '11.7 minutes' into a number of seconds (int)."""
  fields = time_str.split()
  if len(fields) != 2:
    raise ValueError(f'Invalid time string: {time_str!r} has {len(fields)} fields instead of 2.')
  value = float(fields[0])
  unit = fields[1]
  try:
    multiplier = TIME_UNITS[unit]
  except KeyError:
    raise ValueError(f'Invalid time string: unrecognized unit {unit!r}')
  return round(value*multiplier)


def parse_timestamp(ts_str):
  ts_trimmed = re.sub(r' \(\d+ .* ago\)$', '', ts_str)
  dt = datetime.datetime.strptime(ts_trimmed, '%a %d %b %Y %I:%M:%S %p %Z')
  return round(dt.timestamp())


def run_command(*command):
  logging.info(f'Info: Running $ {" ".join(command)}')
  result = subprocess.run(command, encoding='utf8', stdout=subprocess.PIPE)
  return result.stdout.splitlines()


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
