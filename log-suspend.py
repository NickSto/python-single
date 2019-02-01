#!/usr/bin/env python3
import argparse
import logging
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import messaging
assert sys.version_info.major >= 3, 'Python 3 required'

HOOK_NAME = 'systemd-suspend-hook-glue.sh'
LOG_PATH = pathlib.Path('~/aa/computer/logs/power.log').expanduser()
DESCRIPTION = """Log power events as notified by systemd. Also, notify processes of the events via
signals."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('hook_args', nargs='*',
    help='The arguments given to the suspend hook script.')
  parser.add_argument('-p', '--processes', action='append',
    help='Names of processes to notify of power events with signals. The name will be matched '
         'against the basename of the command or its first argument. SIGUSR1 will be sent on '
         'suspend, and SIGUSR2 will be sent on resume.')
  parser.add_argument('-l', '--log', type=pathlib.Path, default=LOG_PATH,
    help='File to log events to. Default: %(default)s')
  parser.add_argument('-i', '--install', action='store_true',
    help='Just install the suspend hook that will invoke this script on suspend and resume. '
         'It will make the hook use whatever arguments you pass along with --install. '
         'The hook will be named '+HOOK_NAME)
  parser.add_argument('-d', '--hook-dir', type=pathlib.Path,
    default=pathlib.Path('/lib/systemd/system-sleep'),
    help='Directory to install the suspend hook into. Default: %(default)s')
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

  logging.basicConfig(stream=args.error_log, level=args.volume, format='%(message)s')

  if args.install:
    script_path = pathlib.Path(__file__).resolve()
    filtered_args = filter_args(argv)
    install(args.hook_dir, HOOK_NAME, script_path, args.log, filtered_args)
  else:
    logging.info('Writing to log {}'.format(args.log))
    with args.log.open('a') as log_file:
      log_file.write('{}\t{}\n'.format(time.time(), '\t'.join(args.hook_args)))
    if args.hook_args == ['pre', 'suspend']:
      signum = signal.SIGUSR1
    elif args.hook_args == ['post', 'suspend']:
      signum = signal.SIGUSR2
    else:
      signum = None
    messaging.send_signals(args.processes, signum)


def filter_args(args):
  """Pass the entire argv and this will remove the command name and any arguments that shouldn't
  be used when executing the hook."""
  filtered_args = []
  omit_next = False
  for arg in args[1:]:
    if omit_next:
      omit_next = False
      continue
    if arg in ('-i', '--install'):
      continue
    if arg in ('-l', '--log'):
      omit_next = True
      continue
    filtered_args.append(arg)
  return filtered_args


def install(hook_dir, hook_name, script_path, log_path, args):
  if not hook_dir.is_dir():
    fail('Error: Suspend hook directory "{}" not found.'.format(hook_dir))
  with tempfile.NamedTemporaryFile(mode='wt', prefix='hook.', suffix='.sh', delete=False) as hook_file:
    hook_file.write('#!/bin/sh\n\n')
    hook_file.write('{} --log {} {} $1 $2\n\n'.format(script_path, log_path, ' '.join(args)))
    temp_hook = hook_file.name
  os.chmod(temp_hook, 0o775)
  hook_path = hook_dir/hook_name
  logging.info('Installing hook script at {}'.format(hook_path))
  result = run_command(['sudo', 'mv', temp_hook, str(hook_path)])
  if not result:
    fail('Error: Failed to move hook script into system directory.')


def run_command(command):
  try:
    result = subprocess.run(command)
  except OSError:
    return False
  except subprocess.CalledProcessError:
    return False
  if result.returncode != 0:
    return False
  return True


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
