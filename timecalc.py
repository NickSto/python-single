#!/usr/bin/env python3
import argparse
import logging
import math
import string
import sys
import typing

DESCRIPTION = """Do arithmetic on time values like "1:30\""""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('args', nargs='+',
    help='The expression to compute')
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

  tokens = parse_args(args.args)

  for token in tokens:
    logging.info(f'{token.type:9}{token.value!r}')

  code_str = concat_tokens(tokens)

  math_props = {key:value for key, value in vars(math).items() if not key.startswith('_')}

  result = eval(code_str, math_props)

  logging.info(f'Result: {result!r}')

  print(human_time(result))


def parse_args(args):
  tokens = []
  for arg in args:
    arg_tokens = tokenize(arg)
    if tokens:
      tokens.append(Token.make('space', ' '))
    tokens.extend(arg_tokens)
  return tokens


class Token(typing.NamedTuple):
  type: str
  value: None

  @classmethod
  def make(cls, type_, raw_value):
    if type_ in ('int_time', 'float_time'):
      value = str(parse_time(raw_value))
    else:
      value = raw_value
    return cls(type=type_, value=value)


def tokenize(text):
  tokens = []
  start = 0
  current_type = 'start'
  for i, char in enumerate(text):
    if char == ' ':
      # Space
      # Don't count consecutive space characters (collapse them into one).
      if current_type != 'space' and current_type != 'start':
        # Store the last token if there was one (i > 0) and it wasn't a space.
        tokens.append(Token.make(current_type, text[start:i]))
      current_type = 'space'
      start = i
    elif char in string.whitespace:
      # Non-space whitespace
      if current_type != 'whitespace' and current_type != 'start':
        tokens.append(Token.make(current_type, text[start:i]))
        start = i
      current_type = 'whitespace'
    elif char in string.digits:
      # Int
      if current_type in ('dot', 'float'):
        current_type = 'float'
      elif current_type in ('int_time', 'float_time', 'identifier'):
        pass
      elif current_type != 'int' and current_type != 'start':
        tokens.append(Token.make(current_type, text[start:i]))
        start = i
        current_type = 'int'
      else:
        current_type = 'int'
    elif char == '.':
      # Dot
      if current_type == 'int':
        current_type = 'float'
      elif current_type == 'int_time':
        current_type = 'float_time'
      else:
        tokens.append(Token.make(current_type, text[start:i]))
        start = i
        current_type = 'dot'
    elif char == ':':
      # Time
      if current_type in ('int', 'int_time'):
        current_type = 'int_time'
      else:
        if current_type == 'float_time':
          # Maybe there could be situations where something like '12:17.3:' could be part of valid
          # syntax. So let it pass, but at least print a warning.
          logging.warning(f'Encountered a float in the middle of a time (char {i+1}) in {text!r}')
        tokens.append(Token.make(current_type, text[start:i]))
        start = i
        current_type = 'other'
    elif char in string.ascii_letters:
      # Identifier
      if current_type == 'identifier':
        pass
      else:
        tokens.append(Token.make(current_type, text[start:i]))
        start = i
        current_type = 'identifier'
    else:
      # Other
      if current_type != 'other' and current_type != 'start':
        tokens.append(Token.make(current_type, text[start:i]))
        start = i
      current_type = 'other'
  if current_type != 'start':
    tokens.append(Token.make(current_type, text[start:]))
  return tokens


def parse_time(time_str):
  """Turn a string like `"1:20"` into a number like `80`.
  Examples:
    20 -> 20
    1:20 -> 80
    1:00:01 -> 3601
    1:20.7 -> 80.7"""
  total = 0
  fields = time_str.split(':')
  for i, field in enumerate(reversed(fields)):
    try:
      value = int(field)
    except ValueError:
      value = float(field)
    total += value * 60**i
  return total


def concat_tokens(tokens):
  return ''.join([token.value for token in tokens])


def human_time(total_seconds, omit_sec=False):
  seconds = total_seconds % 60
  if omit_sec and seconds > 30:
    # If we're not showing minutes, round to the closest minute instead of always rounding down.
    total_seconds = total_seconds + 30
    seconds = total_seconds % 60
  if seconds == int(seconds):
    seconds = int(seconds)
  total_minutes = total_seconds // 60
  minutes = int(total_minutes % 60)
  total_hours = total_minutes // 60
  hours = int(total_hours % 24)
  days = int(total_hours // 24)
  if days == 1:
    days_str = '1 day '
  else:
    days_str = '{} days '.format(days)
  hours_str = '{}:'.format(hours)
  minutes_str = '{}:'.format(minutes)
  seconds_str = '{}'.format(seconds)
  if minutes < 10 and total_minutes >= 60:
    minutes_str = '0{}:'.format(minutes)
  if seconds < 10 and total_seconds >= 60:
    seconds_str = '0{}'.format(seconds)
  elif total_seconds < 60:
    seconds_str = str(seconds)
  if days == 0:
    days_str = ''
    if hours == 0:
      hours_str = ''
      if minutes == 0:
        minutes_str = ''
        if seconds == 0:
          seconds_str = '0s'
  if omit_sec:
    seconds_str = ''
    if minutes == 0:
      if total_seconds < 600:
        minutes_str = '0'
      else:
        minutes_str = '00'
    elif minutes_str.endswith(':'):
      minutes_str = minutes_str[:-1]
  return days_str+hours_str+minutes_str+seconds_str


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
