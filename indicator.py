#!/usr/bin/env python3
import argparse
import collections
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
STATS_LOG = DATA_DIR / 'indicator.json'
NOW = int(time.time())
IGNORE_SSIDS = ('Just an ordinary toaster.', 'Just a 5GHz toaster.')

CHAR_WIDTHS = {'A':9, 'B':8, 'C':8, 'D':8.5, 'E':7, 'F':7, 'G':8.5, 'H':8, 'I':2, 'J':6.5, 'K':8,
  'L':6.5, 'M':11, 'N':9, 'O':10, 'P':8, 'Q':10, 'R':7.5, 'S':7, 'T':8, 'U':8, 'V':9, 'W':13, 'X':9,
  'Y':8, 'Z':7.5, 'a':6.5, 'b':6.5, 'c':6.5, 'd':7.5, 'e':7.5, 'f':4.5, 'g':6.5, 'i':1.5, 'j':2.5,
  'k':6.5, 'l':2.5, 'm':10.5, 'n':6.5, 'o':7.5, 'p':6.5, 'q':7.5, 'r':4.5, 's':5.5, 't':4.5,
  'u':6.5, 'v':7, 'w':9.5, 'x':6, 'y':7.25, 'z':6.5, '0':7.5, '1':4.5, '2':7.25, '3':6, '4':7.5,
  '5':6.5, '6':7, '7':7, '8':7, '9':7.5, '!':2, '"':4.5, '#':9, '$':6.5, '%':11, '&':9, "'":1.5,
  '(':3.5, ')':3.5, '*':6, '+':7, ',':2, '-':3.5, '.':2, '/':6, ':':2, ';':2, '<':7, '=':7, '>':7,
  '?':5, '@':12, '\\':6.5, '^':8, '_':8, '`':2.5, '|':2, '~':7, '[':2, ']':2, '{':3, '}':3, ' ':2,
  '•':4.5, '·':2, '°':4, '…':12}

# List default fields one-per-line for easy commenting out.
FIELDS = []
FIELDS.append('wifilogin')
FIELDS.append('lastping')
FIELDS.append('pings')
FIELDS.append('worktime')
FIELDS.append('disk')
FIELDS.append('temp')
FIELDS.append('ssid')
FIELDS.append('timestamp')

FIELDS_META = {
  'wifilogin': {'priority':70, 'truncate_length':35},
  'lastping':  {'priority':20, 'max_length':20},
  'pings':     {'priority':10, 'max_length':10},
  'worktime':  {'priority':30, 'max_length':16},
  'disk':      {'priority':60, 'max_length':20},
  'temp':      {'priority':40, 'max_length':5},
  'ssid':      {'priority':50, 'truncate_length':9},
  'timestamp': {'priority':80, 'max_length':10},
}

DESCRIPTION = """Gather system info and format it for display in indicator-sysmonitor."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('fields', nargs='*', default=FIELDS,
    help='The fields to include and their order. Give each as a separate argument. '
         'Available fields are "'+'", "'.join(FIELDS_META.keys())+'". '
         'Default: '+' '.join(FIELDS))
  parser.add_argument('-m', '--max-length', type=int, default=250,
    help='The maximum width of the final string, in pixels. If the final string is longer than '
         'this, shorten it by truncating or omitting fields. Default: %(default)s')
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

  run_stats = collections.defaultdict(lambda: None)
  if STATS_LOG.is_file() and os.path.getsize(STATS_LOG) > 0:
    try:
      with STATS_LOG.open('r') as stats_log_file:
        run_stats = json.load(stats_log_file)
    except json.decoder.JSONDecodeError as error:
      with STATS_LOG.open('r') as stats_log_file:
        logging.error('Error: Problem loading stats file "{}":\n'
                      '{}\nFile contents:\n{}'.format(STATS_LOG, error, stats_log_file.read(1024)))
    except OSError:
      logging.info('Info: "{}" could not be found or read. Using default data.'.format(STATS_LOG))

  fitting_fields = status.get_fitting_fields(max_length=args.max_length)
  stable_fields = status.get_stable_fields(run_stats.get('fitting_fields'),
                                           run_stats.get('stable_fields'))
  status.out_str, width = status.format_and_truncate_output_string(stable_fields, args.max_length)
  print(status.out_str)

  run_stats = {'fitting_fields':fitting_fields, 'stable_fields':stable_fields}
  with STATS_LOG.open('w') as stats_log_file:
    json.dump(run_stats, stats_log_file)


class Status():

  def __init__(self, fields=FIELDS):
    self.fields = fields
    self.statuses = None
    self.fitting_fields = None
    self.out_str = None

  def get_fitting_fields(self, max_length=None):
    if self.statuses is None:
      self.statuses = self.get_statuses()
    logging.info('Info: Max length: {}'.format(max_length))
    self.fitting_fields = self.fields
    self.out_str, width = self.format_and_truncate_output_string(self.fields, max_length=max_length)
    # If it's too long, drop fields until it fits.
    if max_length is not None and width > max_length:
      logging.info('Info: Still too long. Trying to drop fields..')
      self.fitting_fields, self.out_str = self.drop_fields_until_fit(self.fields, max_length)
    return self.fitting_fields

  #TODO: It's possible (but unlikely) to get into a situation where we're bouncing between states
  #      but both states are different from the previous fitting and stable fields. This could
  #      happen if, say, the stats file is old. But it could also happen in the normal course of
  #      things.
  #      In this case, it will be stuck showing the old stable fields until it stops bouncing.
  #      It's an unlikely situation and unlikely to persist for long, but something to be aware of.
  def get_stable_fields(self, prev_fitting, prev_stable):
    """Compare what we want to display this time to last run's results and decide what to show.
    This avoids the situation where the display is bouncing between two sets of display fields
    because it's just on the edge of the maximum width.
    This algorithm basically waits to see if any change in the displayed fields is persistent before
    accepting it."""
    if prev_fitting is None or prev_stable is None:
      return self.fitting_fields
    # If we want to display the same fields as were shown last time, we're all good.
    if self.fitting_fields == prev_stable:
      logging.debug('Debug: Fitting fields same as last run\'s stable fields.\n'
                    '       Going with our fitting fields.')
      return self.fitting_fields
    # If we want to display a different set of fields than we showed last time, but it's the same
    # set we wanted to display last time, that means the change is sticky. Time to switch to it.
    if self.fitting_fields == prev_fitting:
      logging.info('Info: Fitting fields different from last run\'s stable fields but same as its '
                   'fitting fields.\n'
                   '      Going with our fitting fields.')
      return self.fitting_fields
    # But if we want to display something different from both (something new), then for now let's
    # stick with what we did last time and wait to see if the change is persistent. If we want to
    # display these fields twice in a row, then it's not just transient and we should switch to it.
    logging.info('Info: Fitting fields differed from last run\'s fitting and stable fields.\n'
                 '      Going with last run\'s stable fields.')
    return prev_stable

  def drop_fields_until_fit(self, fields, max_length):
    priorities = sorted(FIELDS_META.keys(), key=lambda field: -FIELDS_META[field]['priority'])
    fitting_fields = fields
    for field_to_drop in priorities:
      logging.info('Info:   Dropping "{}"..'.format(field_to_drop))
      fitting_fields.remove(field_to_drop)
      out_str = self.format_output_string(fitting_fields, truncate=True)
      width = get_display_width(out_str)
      logging.info('Info: Length: {} after dropping "{}".'.format(width, field_to_drop))
      if width < max_length:
        logging.info('Info: Output is now short enough.')
        break
      if len(fitting_fields) == 0:
        logging.warning('Warning: Failed to shorten output enough.')
        break
    return fitting_fields, out_str

  def format_and_truncate_output_string(self, fields, max_length=None):
    out_str = self.format_output_string(fields, truncate=False)
    width = get_display_width(out_str)
    if max_length is not None and width > max_length:
      logging.info('Info: Too long. Trying to truncate..')
      out_str = self.format_output_string(fields, truncate=True)
      width = get_display_width(out_str)
      logging.info('Info: Length: {} after truncation'.format(width))
    else:
      logging.info('Info: Length: {}'.format(width))
    return out_str, width

  def format_output_string(self, fields, truncate=False):
    out_str = ''
    for field in fields:
      status = self.statuses.get(field)
      if status is None:
        continue
      status = str(status)
      if truncate and 'truncate_length' in FIELDS_META[field]:
        status = truncate_str(status, FIELDS_META[field]['truncate_length'])
      out_str += '[ '+status+' ]'
    return out_str

  def get_statuses(self):
    statuses = {}
    for field in self.fields:
      status = self.get_status(field)
      if status is None:
        logging.info('Info: None status from get_'+field+'()')
      statuses[field] = status
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
      return ssid

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
      if filesystem.startswith('/dev/sr'):
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
    if age > timeout and pings != 'OFFLINE':
      pings = 'STALLED'
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

  def get_wifilogin(self):
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
    return message


class StatusException(Exception):
  def __init__(self, message):
    self.message = message
    self.args = (message,)


def truncate_str(string, max_length):
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


def get_display_width(string):
  width = 0
  for char in string:
    width += CHAR_WIDTHS.get(char, 7)
  return width


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
