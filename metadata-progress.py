#!/usr/bin/env python3
import argparse
import datetime
import logging
import os
import pathlib
import re
import subprocess
import sys
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('old_log', metavar='old-snapshot-log.tsv', nargs='?', type=pathlib.Path,
    help='')
  options.add_argument('new_log', metavar='new-snapshot-log.tsv', nargs='?', type=pathlib.Path,
    help='')
  options.add_argument('-d', '--snap-dir', metavar='snap/dir', type=pathlib.Path,
    help='The directory holding snapshots and their log files. Must be given if either positional '
      'is omitted.')
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

  if args.snap_dir is None and (args.old_log is None or args.new_log is None):
    fail('--snap-dir must be given if old_log or new_log are omitted.')

  if args.old_log:
    old_log = args.old_log
  else:
    old_log = get_log_file(args.snap_dir, 'oldest')
  if args.new_log:
    new_log = args.new_log
  else:
    new_log = get_log_file(args.snap_dir, 'newest')

  if is_process_running():
    show_eta(old_log, new_log)
  else:
    notify('Snapshot not running.')

  plot_progress(old_log, new_log)


def get_log_file(snap_dir, which):
  logs = []
  for log in snap_dir.iterdir():
    if log.name.startswith('log.snapshot-20') and log.name.endswith('.tsv'):
      logs.append(log)
  logs.sort(key=lambda log: os.path.getmtime(log))
  if not logs:
    fail(f'No logs found in {str(snap_dir)!r}')
  if which == 'newest':
    return logs[-1]
  elif which == 'oldest':
    return logs[0]


def is_process_running():
  process = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE, encoding='utf8')
  for line_raw in process.stdout:
    fields = line_raw.split()
    if len(fields) > 11 and fields[11].endswith('file-metadata.py'):
      return True
  return False


def show_eta(old_log, new_log):
  try:
    eta = get_eta(old_log, new_log)
  except RuntimeError:
    pass
  else:
    human_eta = human_time(eta)
    print(human_eta)
    notify(f'ETA: {human_eta}')


def get_eta(old_log, new_log):
  new_start, start_bytes, start_files = get_start(new_log)
  new_current, current_bytes, current_files = get_end(new_log)
  old_start, old_intersect, old_end = find_old_intersect(old_log, current_bytes)
  return calc_remaining(new_start, new_current, old_start, old_intersect, old_end)


def get_start(log_path):
  with log_path.open() as log_file:
    for line_raw in log_file:
      return parse_log_line(line_raw)


def get_end(log_path):
  line_raw = tail(log_path)
  if not line_raw:
    raise RuntimeError
  return parse_log_line(line_raw)


def find_old_intersect(old_log, current_bytes):
  start_time = last_time = last_bytes = intersect_time = None
  for this_time, this_bytes, this_files in read_log(old_log):
    if start_time is None:
      start_time = this_time
    if intersect_time is None and this_bytes > current_bytes:
      if last_time is None or last_bytes is None:
        raise RuntimeError
      logging.debug(f'bytes: {this_bytes}, last_bytes: {last_bytes}, time: {this_time}, last_time: {last_time}')
      rate = (this_bytes-last_bytes)/(this_time-last_time)
      logging.debug(f'rate: {int(rate)} bytes/sec')
      intersect_time = ((current_bytes-last_bytes)/rate) + last_time
      logging.debug(f'intersect_time: {int(intersect_time)} ({intersect_time-last_time:0.2f} sec from last_time)')
    last_time = this_time
    last_bytes = this_bytes
  end_time = last_time
  return start_time, round(intersect_time), end_time


def calc_remaining(new_start, new_current, old_start, old_intersect, old_end):
  new_elapsed = new_current - new_start
  old_elapsed = old_intersect - old_start
  relative_speed = new_elapsed/old_elapsed
  old_remaining = old_end - old_intersect
  logging.debug(f'new_start: {new_start}, new_current:   {new_current}')
  logging.debug(f'old_start: {old_start}, old_intersect: {old_intersect}, old_end: {old_end}')
  return old_remaining*relative_speed


def read_log(log_path):
  with log_path.open() as log_file:
    for line_raw in log_file:
      yield parse_log_line(line_raw)


def parse_log_line(line_raw):
  fields = line_raw.rstrip('\r\n').split('\t')
  try:
    this_time = int(fields[0])
    this_bytes = int(fields[1])
    this_files = int(fields[2])
  except (IndexError, ValueError):
    raise RuntimeError
  return this_time, this_bytes, this_files


def plot_progress(old_log, new_log):
  cmd = ['scatterplot.py', '-g', '1', '-x', '2', '-y', '3', '-X', 'Hours', '-Y', 'GB']
  process = subprocess.Popen(cmd, stdin=subprocess.PIPE, encoding='utf8')
  for line_raw in get_plot_lines(old_log, new_log):
    process.stdin.write(line_raw)
  process.stdin.close()


def get_plot_lines(old_log, new_log):
  old_name = get_name(old_log.name, 'Old')
  new_name = get_name(new_log.name, 'New')
  for this_time, this_bytes in get_plot_data(old_log):
    yield format_plot_data(old_name, this_time, this_bytes)
  for this_time, this_bytes in get_plot_data(new_log):
    yield format_plot_data(new_name, this_time, this_bytes)


def format_plot_data(label, this_time, this_bytes):
  return f'{label}\t{this_time/60/60}\t{this_bytes/1024/1024/1024}\n'


def get_plot_data(log_path):
  start_time = None
  for this_time, this_bytes, this_files in read_log(log_path):
    if start_time is None:
      start_time = this_time
    relative_time = this_time - start_time
    yield relative_time, this_bytes


def get_name(filename, default=None):
  match = re.search(r'20[12]\d-[012]\d-[0-3]\d', filename)
  if not match:
    return default
  date = match.group()
  today = datetime.datetime.now().strftime('%Y-%m-%d')
  if date == today:
    return 'Today'
  else:
    return date


def tail(path, lines=1):
  result = subprocess.run(['tail', '-n', str(lines), path], stdout=subprocess.PIPE, encoding='utf8')
  return result.stdout


def notify(title, body=None):
  cmd = ['notify-send', title]
  if body:
    cmd.append(body)
  subprocess.run(cmd)


def human_time(sec):
  if sec < 60:
    return format_time(sec, 'second')
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
  except BrokenPipeError:
    pass
