#!/usr/bin/env python3
import argparse
import logging
import subprocess
import sys
import time
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Monitor a running process and, optionally, keep it running."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('command', nargs='*',
    help='A command to execute on startup and when this detects the process has died. If omitted, '
         'this script will run until the monitored process dies, then exit. But if a command is '
         'given, this will run indefinitely, restarting the process whenever it dies. The only way this will exit is if '
         'this Python script dies, or if the monitored process dies right on launch (within '
         '--setup-time seconds).')
  parser.add_argument('-a', '--arg', nargs=2, action='append', dest='args',
    help='An argument in the command you want to monitor. Give a number and the string, like '
         '"--arg 1 file.txt". This means this will find any command whose first argument in the '
         'command line (ARGV[1]) is "file.txt". You can also specify argument 0 (the executable). '
         'Give --arg multiple times to specify multiple search terms (which must all match).')
  parser.add_argument('-p', '--pause', type=int, default=5,
    help='Number of seconds to wait between checks. Default: %(default)s.')
  parser.add_argument('-s', '--setup-time', type=int, default=5,
    help='Number of seconds to wait for the relaunch command to get going before checking on its '
         'status. If the process isn\'t found after this amount of time, it will assume the '
         'command didn\'t work and exit (instead of retrying infinitely).')
  parser.add_argument('-l', '--log', type=argparse.FileType('a'),
    help='Write stats on the process to this file.')
  parser.add_argument('-L', '--error-log', type=argparse.FileType('w'), default=sys.stderr,
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

  cmd_args = process_cmd_args(args.args)

  if args.command:
    logging.info('Info: Launching process..')
    run_in_background(args.command, args.setup_time)

  missing = True
  while True:
    found = monitor(cmd_args, args.pause)
    if found:
      missing = False
      logging.info('Info: Process exited or died.')
      if args.command:
        logging.info('Restarting..')
        run_in_background(args.command, args.setup_time)
    elif missing:
      logging.error('Error: Process not found.')
      break
    else:
      if args.command:
        logging.error('Error: Process did not restart successfully.')
      break


def process_cmd_args(cmd_args_raw):
  cmd_args = []
  for pos_str, arg in cmd_args_raw:
    try:
      position = int(pos_str)
    except ValueError:
      fail('Error: Invalid argument number in --arg {!r} {!r}'.format(pos_str, arg))
    cmd_args.append({'position':position, 'arg':arg})
  return cmd_args


def run_in_background(command, pause):
  logging.info('$ '+' '.join(command))
  subprocess.Popen(command)
  time.sleep(pause)


def monitor(cmd_args, pause=15):
  """Monitor the process, and return once it's no longer alive.
  Return `found`: whether the process was ever found."""
  alive = True
  found = False
  while alive:
    ps_proc = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE)
    alive = False
    for line_raw in ps_proc.stdout:
      line = str(line_raw, 'ascii').rstrip('\r\n')
      fields = line.split()
      match = True
      for cmd_arg in cmd_args:
        position = cmd_arg['position']
        if not (len(fields) > 10+position and fields[10+position] == cmd_arg['arg']):
          match = False
      if match:
        alive = True
        found = True
        logging.debug(line)
    if alive:
      time.sleep(pause)
  return found


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
