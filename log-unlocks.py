#!/usr/bin/env python3
import argparse
import logging
import os
import pathlib
import signal
import subprocess
import sys
import time
import messaging
assert sys.version_info.major >= 3, 'Python 3 required'

LOG_PATH = pathlib.Path('~/aa/computer/logs/power.log').expanduser()
DESCRIPTION = """Log screen lock/unlock events as notified by DBus. Also, notify processes of the
events via signals."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('-p', '--processes', action='append',
    help='Names of processes to notify of unlock events with signals. The name will be matched '
         'against the basename of the command or its first argument. SIGUSR1 will be sent on '
         'lock, and SIGUSR2 will be sent on unlock.')
  parser.add_argument('-l', '--log', type=pathlib.Path, default=LOG_PATH,
    help='File to log events to. Default: %(default)s')
  parser.add_argument('-L', '--error-log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


#TODO: Pure Python strategy:
#      https://stackoverflow.com/questions/11544836/monitoring-dbus-messages-by-python
#      But replace `gobject` with `GLib` (imported from gi.repository).


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])
  log_file = args.log.open('a')

  logging.basicConfig(stream=args.error_log, level=args.volume, format='%(message)s')

  for event in get_lock_events():
    if event == 'lock':
      logging.info('Info: Screen locked.')
      messaging.send_signals(args.processes, signal.SIGUSR1)
      print(f'{time.time()}\tpre\tlock', file=log_file)
      log_file.flush()
    elif event == 'unlock':
      logging.info('Info: Screen unlocked.')
      messaging.send_signals(args.processes, signal.SIGUSR2)
      print(f'{time.time()}\tpost\tlock', file=log_file)
      log_file.flush()


def get_lock_events():
  command = get_dbus_command()
  logging.info('DBus command: $ '+' '.join(command))
  process = run_command(command)
  return filter_for_lock_events(process.stdout)


def get_dbus_command():
  """Construct the dbus-monitor command.
  If we can find the bus address, it will be something like:
  $ dbus-monitor --address unix:path=/run/user/1000/bus "type='signal',interface='org.gnome.ScreenSaver'"
  Otherwise, it will be:
  $ dbus-monitor --session "type='signal',interface='org.gnome.ScreenSaver'"
  """
  command = ['dbus-monitor']
  bus_address = get_session_bus_address()
  if bus_address is None:
    command.append('--session')
  else:
    command.append('--address')
    command.append(bus_address)
  command.append("type='signal',interface='org.gnome.ScreenSaver'")
  return command


def run_command(command):
  try:
    process = subprocess.Popen(command, encoding='utf8', stdout=subprocess.PIPE)
  except (OSError, subprocess.CalledProcessError) as error:
    logging.critical(f'Critical: Failure to execute command {command!r}: {error}')
    raise
  return process


def filter_for_lock_events(event_stream):
  correct_signal = False
  for line_raw in event_stream:
    fields = line_raw.split()
    if correct_signal and len(fields) == 2 and fields[0] == 'boolean':
      if fields[1] == 'true':
        yield 'lock'
      elif fields[1] == 'false':
        yield 'unlock'
      correct_signal = False
    elif 'path=/org/gnome/ScreenSaver;' in fields and 'member=ActiveChanged' in fields:
      correct_signal = True


def get_session_bus_address():
  for pid in get_session_bus_processes():
    address = get_dbus_environ(pid)
    if address:
      return address


def get_session_bus_processes():
  for pid in messaging.find_processes(('dbus-daemon',)):
    yield pid
  for pid, argv in messaging.list_processes():
    if len(argv) <= 0:
      continue
    cmd = argv[0]
    base_cmd = os.path.split(cmd)[1]
    if base_cmd.startswith('gnome-session'):
      yield pid


def get_dbus_environ(pid):
  variables = messaging.get_environ_vars(pid)
  if variables and 'DBUS_SESSION_BUS_ADDRESS' in variables:
    return variables['DBUS_SESSION_BUS_ADDRESS']


def fail(message):
  logging.critical('Critical: '+str(message))
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception('Unrecoverable error')


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
