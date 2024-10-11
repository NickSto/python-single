#!/usr/bin/env python3
import argparse
import datetime
import logging
import subprocess
import sys
import time
assert sys.version_info.major >= 3, 'Python 3 required'

USAGE = '$ %(prog)s [options] goal command [args]'
DESCRIPTION = """Estimate the time to reach a goal count."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, usage=USAGE, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('goal', type=float,
    help='The goal count.')
  options.add_argument('command', nargs=argparse.REMAINDER,
    help='The command to execute to produce a count.')
  options.add_argument('-f', '--field', type=int,
    help='The whitespace-delimited field of the output to use as the count (1-based).')
  options.add_argument('-e', '--eval', action='store_true', default=False,
    help='The first "command" argument is a full command line. Execute as a literal shell line.')
  options.add_argument('-p', '--pause', type=float, default=5*60,
    help='Seconds to wait between checks. Default: %(default)d')
  options.add_argument('-i', '--initial-pause', type=int, default=15,
    help='Seconds to wait before the second check (the first one that gives an ETA). '
      'Default: %(default)s')
  options.add_argument('-t', '--start-time', type=int, default=time.time(),
    help='The starting time, if continuing from a previous run.')
  options.add_argument('-s', '--start-count', type=float,
    help='The starting number, if continuing from a previous run.')
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

  if args.eval and len(args.command) > 1:
    fail('The command line should be a single, quoted argument when using --eval.')

  if args.start_count is not None:
    start_count = args.start_count
  else:
    start_count = get_current_count(args.command, args.field, args.eval)

  start = int(args.start_time)
  ratio = start_count/args.goal
  print(f'Initial time: {start} | Initial count: {start_count} ({ratio:0.1%}) | Goal: {args.goal}')

  watch_progress(
    args.start_time, start_count, args.goal, args.command, args.field, args.pause, args.eval,
    args.initial_pause
  )

  elapsed_str = human_time_amount(time.time() - args.start_time)
  print(f'Goal reached! Total time: {elapsed_str}')


def watch_progress(start_time, start_count, goal, command, field, pause, eval_, initial_pause):
  first_loop = True
  current_count = last_count = start_count
  remaining = 1
  while remaining > 0:
    first_loop = sleep(pause, initial_pause, first_loop)
    current_count = get_current_count(command, field, eval_)
    if current_count == start_count:
      logging.warning(f'No progress yet! Count at {current_count}')
      continue
    now = time.time()
    remaining = calc_remaining(start_count, start_time, current_count, now, goal)
    if remaining > 0:
      print(format_status(current_count, last_count, goal, now, remaining))
    last_count = current_count


def sleep(pause, initial_pause, first_loop):
  if first_loop:
    time.sleep(initial_pause)
    first_loop = False
  else:
    time.sleep(pause)
  return first_loop


def get_current_count(command, field, eval_):
  result = subprocess.run(command, shell=eval_, encoding='utf8', stdout=subprocess.PIPE)
  return parse_result(result.stdout, field)


def parse_result(result_str, field):
  lines = result_str.splitlines()
  if not lines:
    raise ValueError('No output returned from command')
  last_line = lines[-1]
  if field:
    fields = last_line.split()
    if len(fields) < field:
      raise ValueError(f'Too few fields in output: {len(fields)} < {field}')
    value_str = fields[field-1]
  else:
    value_str = last_line
  try:
    return int(value_str)
  except ValueError:
    return float(value_str)


def format_status(current_count, last_count, goal, now, remaining):
  diff = current_count - last_count
  sign = '' if diff < 0 else '+'
  current_str = f'Current: {current_count} ({sign}{diff}, {current_count/goal:0.1%})'
  if remaining == float('inf'):
    return f'{current_str} | ETA: ??? (count has decreased)'
  else:
    remaining_str = human_time_amount(remaining)
    eta_str = human_timestamp(now+remaining)
    return f'{current_str} | ETA: {eta_str} ({remaining_str})'


def calc_remaining(start_count, start_time, current_count, current_time, goal):
  if goal > start_count:
    # We're counting up to the goal.
    progress = current_count - start_count
    count_left = goal - current_count
  else:
    # We're counting down to the goal.
    progress = start_count - current_count
    count_left = current_count - goal
  if progress < 0:
    return float('inf')
  else:
    elapsed = current_time - start_time
    count_per_sec = progress / elapsed
    return count_left / count_per_sec


def human_timestamp(timestamp):
  now = datetime.datetime.now()
  then = datetime.datetime.fromtimestamp(timestamp)
  if then.strftime('%Y-%m-%d') == now.strftime('%Y-%m-%d'):
    # It's today. Just return the time.
    return then.strftime(f'{get_12hr(then):2d}:%M:%S %p')
  elif then - now < datetime.timedelta(weeks=12):
    # It's another day, but within 3 months.
    return then.strftime(f'%b {then.day:2d} {get_12hr(then):2d}:%M %p')
  elif then - now < datetime.timedelta(days=364):
    # It's within a year.
    return then.strftime(f'%b {then.day:2d}')
  else:
    # It's over a year from now.
    return then.strftime('%Y-%m-%d')


def get_12hr(dt):
  """Get the 12-hour clock version of the hour, but with no padding."""
  # A simple modulo 12 wouldn't do it, since 12 % 12 = 0.
  return ((dt.hour-1) % 12) + 1


def human_time_amount(sec):
  if sec < 60:
    return format_time(round(sec), 'second')
  elif sec < 60*60:
    return format_time(sec/60, 'minute')
  elif sec < 24*60*60:
    return format_time(sec/60/60, 'hour')
  elif sec < 10*24*60*60:
    return format_time(sec/60/60/24, 'day')
  elif sec < 40*24*60*60:
    return format_time(sec/60/60/24/7, 'week')
  elif sec < 365*24*60*60:
    return format_time(sec/60/60/24/30.5, 'month')
  else:
    return format_time(sec/60/60/24/365, 'year')


def format_time(quantity, unit):
  rounded = round(quantity, 1)
  if rounded == int(quantity):
    rounded = int(quantity)
  output = str(rounded)+' '+unit
  if rounded != 1:
    output += 's'
  return output


def fail(message):
  logging.critical('Error: '+str(message))
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception(message)


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except (KeyboardInterrupt, BrokenPipeError):
    pass
