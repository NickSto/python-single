#!/usr/bin/env python3
import argparse
import configparser
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
IGNORE_SSIDS = ('Just an ordinary toaster.', 'Just a 5GHz toaster.')

# List default fields one-per-line for easy commenting out.
FIELDS = []
FIELDS.append('wifilogin')
FIELDS.append('lastping')
FIELDS.append('pings')
FIELDS.append('worktime')
# FIELDS.append('disk')
FIELDS.append('temp')
FIELDS.append('ssid')
# FIELDS.append('timestamp')

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
        logging.info('Info: None status from get_'+field+'()')
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

  def get_ssid(self, max_length=11):
    cmd_output = run_command(['iwconfig'])
    if cmd_output is None:
      return
    ssid = None
    for line in cmd_output.splitlines():
      match = re.search(r'^.*SSID:"(.*)"\s*$', line)
      if match:
        ssid = match.group(1)
    if ssid in IGNORE_SSIDS:
      return None
    else:
      return truncate(ssid, max_length)

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
      elif ratio > 100:
        ratio_str = str(int(ratio))
      elif ratio > 10:
        ratio_str = '{:0.1f}'.format(ratio)
      else:
        ratio_str = '{:0.2f}'.format(ratio)
      if output:
        output = '{} · {}'.format(output, ratio_str)
      else:
        output = ratio_str
    return output

  def get_pings(self):
    if not hasattr(self, 'pings'):
      self.pings, self.lastping = self.get_pings_and_lastping()
    return self.pings

  def get_lastping(self):
    if not hasattr(self, 'lastping'):
      self.pings, self.lastping = self.get_pings_and_lastping()
    return self.lastping

  def get_pings_and_lastping(self, timeout=300):
    pings = self.get_provisional_pings()
    try:
      latency, timestamp = self.get_last_ping_data()
    except StatusException as error:
      return None, error.message
    if pings is None:
      return None, None
    # Check if the last ping was dropped.
    if latency == 0.0:
      latency_str = 'DROP'
    elif latency < 100:
      latency_str = '{:0.1f} ms'.format(latency)
    else:
      latency_str = '{} ms'.format(int(latency))
    # How old is the last ping?
    age = NOW - timestamp
    age_str = human_time(age)
    if age < timeout:
      lastping = '{} / {} ago'.format(latency_str, age_str)
    else:
      lastping = 'N/A ms / {} ago'.format(age_str)
    # If ping is old, and upmonitor doesn't say it's offline, assume it's frozen.
    if age > timeout and pings != '[OFFLINE]':
      pings = '[STALLED]'
    return pings, lastping

  def get_provisional_pings(self):
    pings = read_file(DATA_DIR/'upstatus.txt')
    if pings is None:
      return None
    else:
      pings = pings.strip()
    return pings

  def get_last_ping_data(self):
    config_file = DATA_DIR/'upmonitor.cfg'
    if not config_file.is_file():
      raise StatusException('no upmonitor.cfg')
    config = configparser.ConfigParser()
    config.read(config_file)
    try:
      log_path = pathlib.Path(config['args']['logfile'])
    except KeyError:
      raise StatusException('bad upmonitor.cfg')
    if not log_path.is_file():
      raise StatusException('no log')
    with log_path.open() as log_file:
      line = last_line(log_file)
    if line is None:
      raise StatusException('empty log')
    fields = line.split('\t')
    if len(fields) < 2:
      raise StatusException('invalid log')
    try:
      latency = float(fields[0])
      timestamp = int(fields[1])
      return latency, timestamp
    except ValueError:
      raise StatusException('invalid log')

  def get_wifilogin(self, max_length=35):
    # If the wifi-login script is running, include its current status from its log file.
    # Get the log file it's printing to from its entry in ps aux. Also get its pid.
    log_path = None
    pid = None
    for line in run_command(['ps', 'aux']):
      fields = line.split()
      if len(fields) < 12:
        continue
      if not (fields[10].startswith('python') and fields[11].endswith('wifi-login2.py')):
        continue
      found_log_arg = False
      for i, arg in enumerate(fields[12:]):
        if arg == '-l' or arg == '--log':
          found_log_arg = True
        elif found_log_arg:
          log_path = arg
          break
      if log_path is not None:
        pid = fields[1]
        break
    if log_path is None or pid is None:
      return None
    # Make sure `log_path` is absolute.
    if not log_path.startswith('/'):
      # If it's relative, find the process' working directory and prepend with that.
      wd_link = '/proc/{}/cwd'.format(pid)
      if os.path.islink(wd_link):
        working_directory = os.readlink(wd_link)
        assert working_directory.startswith('/'), working_directory
        log_path = os.path.join(working_directory, log_path)
      else:
        return None
    with open(log_path) as log_file:
      line = last_line(log_file)
    if not line:
      return None
    fields = line.split(': ')
    if not fields:
      return None
    level = fields[0]
    #TODO: Check the last few lines and show the highest level message.
    if level.lower() not in ('debug', 'info', 'warning', 'error', 'critical'):
      return None
    message = ': '.join(fields[1:])
    return truncate(message, max_length)


class StatusException(Exception):
  def __init__(self, message):
    self.message = message
    self.args = (message,)


def truncate(string, max_length):
  if string is None:
    return None
  elif len(string) <= max_length+1:
    return string
  else:
    return string[:max_length]+'…'


def read_file(path, max_size=4096):
  try:
    with open(path) as file:
      return file.read(max_size)
  except OSError:
    return None


def run_command(command, stream=False):
  if stream:
    null_value = []
  else:
    null_value = None
  try:
    if stream:
      process = subprocess.Popen(command, stdout=subprocess.PIPE)
      return process.stdout
    else:
      output = subprocess.check_output(command, stderr=subprocess.DEVNULL)
      return str(output, 'utf8').rstrip('\r\n')
  except OSError:
    return null_value
  except subprocess.CalledProcessError:
    return null_value


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


def tail(file, lines):
  # Get last `lines` lines of the file. `file` must be an open filehandle.
  # Returns a list of strings, one per line. If the file is empty, this will return an empty list.
  # Implementation from https://gist.github.com/amitsaha/5990310#gistcomment-2049292
  file.seek(0, os.SEEK_END)
  file_length = position = file.tell()
  line_count = 0
  while position >= 0:
    file.seek(position)
    next_char = file.read(1)
    if next_char == '\n' and position != file_length-1:
      line_count += 1
    if line_count == lines:
      break
    position -= 1
  if position < 0:
    file.seek(0)
  return file.read().splitlines()


def last_line(file):
  lines = tail(file, 1)
  if lines:
    return lines[0]
  else:
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
