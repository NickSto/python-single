#!/usr/bin/env python3
import argparse
import json
import logging
import os
import pathlib
import re
import subprocess
import sys
import time
assert sys.version_info.major >= 3, 'Python 3 required'

DATA_DIR = pathlib.Path('~/.local/share/nbsdata').expanduser()
NOW = int(time.time())

FIELDS = []
FIELDS.append('worktime')
FIELDS.append('disk')
FIELDS.append('temp')
FIELDS.append('ssid')
FIELDS.append('timestamp')

DESCRIPTION = """"""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('fields', nargs='*', default=FIELDS,
    help='The fields to include and their order. Give each as a separate argument. '
         'Default: '+' '.join(FIELDS))
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

  status = Status(args.fields)

  print(status.get_output_string())


class Status():

  def __init__(self, fields=FIELDS):
    self.fields = fields
    self.statuses = None

  def get_output_string(self, statuses=None):
    if statuses is None:
      statuses = self.statuses
    if statuses is None:
      statuses = self.statuses = self.get_statuses()
    out_strs = []
    for status in statuses:
      if status:
        if status.startswith('[ ') and status.endswith(' ]'):
          out_strs.append(status)
        else:
          out_strs.append('[ '+status+' ]')
    return ''.join(out_strs)

  def get_statuses(self, fields=None):
    if fields is None:
      fields = self.fields
    statuses = []
    for field in fields:
      status = self.get_status(field)
      if status is None:
        logging.warning('Warning: None status from get_'+field+'()')
      else:
        statuses.append(str(status))
    return statuses

  def get_status(self, field):
    fxn = getattr(self, 'get_'+field, None)
    if fxn is None:
      return
    else:
      return fxn()

  # Status functions.

  def get_timestamp(self):
    return NOW

  def get_ssid(self):
    max_length = 11
    cmd_output = run_command(['iwconfig'])
    if cmd_output is None:
      return
    ssid = None
    for line in cmd_output.splitlines():
      match = re.search(r'^.*SSID:"(.*)"\s*$', line)
      if match:
        ssid = match.group(1)
    if ssid is None:
      return
    elif len(ssid) <= max_length+1:
      return ssid
    else:
      return ssid[:max_length]+'…'

  def get_disk(self):
    cmd_output = run_command(['df', '-h'])
    if cmd_output is None:
      return
    frees = []
    for line in cmd_output.splitlines():
      fields = line.split()
      filesystem = fields[0]
      free = fields[3]
      mount = fields[5]
      if not filesystem.startswith('/dev/'):
        continue
      if mount.startswith('/snap/') or mount == '/boot' or mount.startswith('/boot'):
        continue
      frees.append(free)
    if frees:
      return ','.join(frees)

  def get_temp(self):
    cmd_output = run_command(['sensors'])
    if cmd_output is None:
      return
    section = 'preamble'
    for line in cmd_output.splitlines():
      if not line:
        section = 'break'
      elif line == 'coretemp-isa-0000':
        section = 'cpu'
      elif section == 'cpu':
        fields1 = line.split(':')
        device = fields1[0].strip()
        fields2 = fields1[1].split()
        temp_str = fields2[0]
        if temp_str.endswith('°C'):
          try:
            temp = float(temp_str[:-2])
          except ValueError:
            return
          return '{:0.0f}°C'.format(temp)

  def get_worktime(self):
    contents = read_file(DATA_DIR/'workstatus.txt')
    if contents is None:
      return
    fields = contents.split()
    if len(fields) < 2:
      return
    mode = fields[0]
    try:
      start = int(fields[1])
    except ValueError:
      return
    elapsed = NOW - start
    elapsed_human = human_time(elapsed, omit_sec=True)
    if mode != 's':
      output = '{} {}'.format(mode, elapsed_human)
    else:
      output = ''
    # Try to get the ratio.
    summary = None
    try:
      with (DATA_DIR/'worksummary.json').open() as file:
        summary = json.load(file)
    except (OSError, json.decoder.JSONDecodeError):
      pass
    ratio = None
    if summary is not None and 'ratios' in summary:
      for ratio_obj in summary['ratios']:
        if ratio_obj.get('timespan') == 43200:
          ratio = ratio_obj.get('value')
    if ratio is not None:
      if ratio > 10000000000:
        ratio_str = '∞'
      else:
        ratio_str = '{:0.2f}'.format(ratio)
      if output:
        output = '{} · {}'.format(output, ratio_str)
      else:
        output = ratio_str
    return output


def read_file(path, max_size=4096):
  try:
    with open(path) as file:
      return file.read(max_size)
  except OSError:
    return None


def run_command(command):
  try:
    output = subprocess.check_output(command, stderr=subprocess.DEVNULL)
  except OSError:
    return None
  except subprocess.CalledProcessError:
    return None
  return str(output, 'utf8').rstrip('\r\n')


def human_time(total_seconds, omit_sec=False):
  seconds = total_seconds % 60
  if omit_sec and seconds > 30:
    # If we're not showing minutes, round to the closest minute instead of always rounding down.
    total_seconds = total_seconds + 30
    seconds = total_seconds % 60
  total_minutes = total_seconds // 60
  minutes = total_minutes % 60
  total_hours = total_minutes // 60
  hours = total_hours % 24
  days = total_hours // 24
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
    seconds_str = '{}s'.format(seconds)
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
