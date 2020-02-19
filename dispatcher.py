#!/usr/bin/env python3
import argparse
import collections
import datetime
import logging
import pathlib
import sys
import yaml
assert sys.version_info.major >= 3, 'Python 3 required'

PERIODS = collections.OrderedDict(
  (
    ('min', {'dt':lambda dt: dt.minute}),
    ('hr',  {'dt':lambda dt: dt.hour}),
    ('dom', {'dt':lambda dt: dt.day}),
    ('mon', {'dt':lambda dt: dt.month}),
    ('week',{'dt':lambda dt: dt.weekday()+1})
  )
)

DESCRIPTION = """Take actions based on the content of a simple input file."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('infile', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='Input file. Omit to read from stdin.')
  options.add_argument('-c', '--config', type=argparse.FileType('r'),
    help='Config file for parameters and options.')
  options.add_argument('-w', '--whitelist', type=pathlib.Path, action='append', default=[],
    help='Allow accessing files under this directory. Can give multiple directories by giving this '
      'option multiple times.')
  options.add_argument('-p', '--precision', type=int,
    help='Time precision of execution. How many minutes since the last time this was executed? '
      'Required for any command with a #?when parameter. Currently only applied to the #?when hour '
      'and minute.')
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

  static_params = {'whitelist':[]}
  if args.config:
    read_config(args.config, static_params)
  for path in args.whitelist:
    static_params['whitelist'].append(path.resolve())

  for lines in chunk_input(args.infile):
    # Parse the chunk.
    try:
      command, chunk_args, params, content = parse_chunk(lines)
    except ValueError as error:
      logging.error(error)
      continue
    # Include static params, but allow them to be overridden by ones from the current chunk.
    for key, value in static_params.items():
      if key not in params:
        params[key] = value
    # Postpone commands according to 'when' parameter.
    if 'when' in params:
      if not execute_now(params['when'], args.precision):
        continue
    # Execute the command.
    fxn = COMMANDS[command]
    fxn(chunk_args, content, params)


def read_config(config_file, params):
  data = yaml.safe_load(config_file)
  if 'whitelist' in data:
    for path_str in data['whitelist']:
      path = pathlib.Path(path_str).expanduser()
      if not path.is_absolute():
        logging.error(f'Error: Config file whitelist path not absolute: {str(path)!r}')
      params['whitelist'].append(path)


def chunk_input(lines):
  chunk_lines = []
  for line_raw in lines:
    line = line_raw.rstrip('\r\n')
    if line.startswith('#!'):
      if chunk_lines:
        yield chunk_lines
      chunk_lines = []
    chunk_lines.append(line)
  if chunk_lines:
    yield chunk_lines


def parse_chunk(chunk_lines):
  if len(chunk_lines) <= 0:
    raise ValueError('Received a chunk with no lines.')
  first_line = chunk_lines[0]
  command, args = parse_command(first_line)
  content = []
  params = {}
  for line in chunk_lines[1:]:
    if not content and line.startswith('#?'):
      param_type, param = parse_params(line)
      params[param_type] = param
    else:
      content.append(line)
  return command, args, params, content


def parse_command(command_line):
  assert command_line.startswith('#!'), command_line
  fields = command_line[2:].split()
  command = fields[0]
  args = fields[1:]
  if command not in COMMANDS:
    raise ValueError(f'Unrecognized command {command!r} in line {command_line!r}')
  return command, args


def parse_params(params_line):
  assert params_line.startswith('#?'), params_line
  fields = params_line[2:].split()
  param_type = fields[0]
  param_args = fields[1:]
  if param_type == 'when':
    return 'when', parse_when_param(param_args)
  else:
    raise ValueError(f'Invalid parameter type {param_type!r}')


def parse_when_param(args):
  if len(args) != len(PERIODS):
    raise ValueError(
      f'Wrong number of arguments to when parameter (saw {len(args)}, need {len(PERIODS)}).'
    )
  time_spec = {}
  for period, arg in zip(PERIODS, args):
    if arg == '*':
      value = None
    else:
      try:
        value = int(arg)
      except ValueError as error:
        error.args = (f'Invalid when parameter {arg!r} (not an integer or *)',)
        raise error
    time_spec[period] = value
  return time_spec


def execute_now(time_spec, precision):
  if precision is None:
    logging.error('Error: Encountered #?when parameter, but no --precision given.')
    return None
  now = datetime.datetime.now()
  # If the time_spec includes a day of any kind, are we on the right day?
  for period, spec_value in time_spec.items():
    if period in ('min', 'hr'):
      continue
    elif spec_value is None:
      continue
    dt_converter = PERIODS[period]['dt']
    current_value = dt_converter(now)
    if current_value != spec_value:
      return False
  # How many minutes after the time_spec are we executing?
  spec_hr = time_spec['hr']
  if spec_hr is None:
    spec_hr = now.hour
  spec_min = time_spec['min']
  if spec_min is None:
    spec_min = now.minute
  spec_minutes = spec_hr*60 + spec_min
  now_minutes = now.hour*60 + now.minute
  diff = now_minutes - spec_minutes
  if diff < 0:
    diff += 24*60
  logging.debug(f'Debug: Got a time diff of {diff} from {now_minutes} - {spec_minutes}')
  if diff < 0:
    raise ValueError(
      f'time_spec seems to be > 24 hrs after now? (time_spec: {time_spec!r}, now: {now!r})'
    )
  if diff > precision:
    return False
  else:
    return True


def do_echo(args, content, params):
  print(*args)


def do_cat(args, content, params):
  whitelist = params.get('whitelist', ())
  for path_str in args:
    path = pathlib.Path(path_str).resolve()
    if not in_whitelist(path, whitelist):
      logging.error(f'Error: Path not in whitelist: {str(path)!r}')
      continue
    if not path.parent.is_dir():
      logging.error(f'Error: Directory containing {str(path)!r} not found.')
      continue
    try:
      with path.open('w') as file:
        for line in content:
          print(line, file=file)
    except OSError as error:
      logging.error(f'Error: Failed writing to file {str(path)!r}: {error}')


COMMANDS = {
  'echo':do_echo,
  'cat':do_cat,
}


def in_whitelist(path, whitelist):
  for directory in whitelist:
    if str(path).startswith(f'{directory}/'):
      return True
  return False


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
