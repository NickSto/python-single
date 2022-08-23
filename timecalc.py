#!/usr/bin/env python3
import argparse
import logging
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

  # For now, only handle a simple expression with two numbers and one operator.
  if len(tokens) != 3:
    fail(f'Expression too long. Currently can only handle 3 tokens (saw {len(tokens)})')
  elif not (tokens[0].is_value() and tokens[1].type == 'operator' and tokens[2].is_value()):
    fail(f'Expression is the wrong form. Currently can only handle [value] [operator] [value].')

  value1 = tokens[0].value
  operator = tokens[1].value
  value2 = tokens[2].value

  if operator == '+':
    result = value1 + value2
  elif operator == '-':
    result = value1 - value2
  elif operator == '*':
    result = value1 * value2
  elif operator == '/':
    result = value1 / value2

  logging.info(f'Result: {result!r}')

  print(human_time(result))


def parse_args(args):
  tokens = []
  for arg in args:
    arg_tokens = tokenize(arg)
    tokens.extend(arg_tokens)
  return tokens


class Token(typing.NamedTuple):
  type: str
  value: None

  def is_value(self):
    return self.type in ('time', 'int', 'float')


def tokenize(text):
  tokens = []
  last = 0
  current_token = None
  for i, char in enumerate(text):
    if char in '-+/*':
      # Operator
      if current_token and i > 0:
        tokens.append(cast_token(current_token, text[last:i]))
      tokens.append(cast_token('operator', char))
      last = i+1
      current_token = None
    elif char in string.whitespace:
      # Whitespace
      if current_token and i > 0:
        tokens.append(cast_token(current_token, text[last:i]))
      last = i+1
      current_token = None
    elif char == ':':
      # Time
      current_token = 'time'
    elif char == '.':
      # Float
      if current_token == 'time':
        raise ValueError(f'Cannot have a colon and period in a value: {text!r}')
      current_token = 'float'
    elif char in string.digits:
      # Integer
      if current_token not in ('time', 'float'):
        current_token = 'int'
    else:
      raise ValueError(f'Invalid character {char!r} in {text!r}')
  if current_token:
    tokens.append(cast_token(current_token, text[last:]))
  return tokens


def cast_token(type_, value_str):
  if type_ == 'time':
    value = parse_time(value_str)
  elif type_ == 'float':
    value = float(value_str)
  elif type_ == 'int':
    value = int(value_str)
  elif type_ == 'operator':
    value = value_str
  else:
    raise ValueError(f'Invalid token type {type_!r}')
  return Token(type=type_, value=value)


def parse_time(time_str):
  """Turn a string like `"1:20"` into an integer like `80`."""
  total = 0
  fields = time_str.split(':')
  for i, field in enumerate(reversed(fields)):
    number = int(field)
    total += number * 60**i
  return total


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
