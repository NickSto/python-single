#!/usr/bin/env python3
import argparse
import logging
import subprocess
import sys
import time
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Launch a process, keep it running, and log statistics on its uptime. This is
basically run-one-constantly, but with stats logging."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('command', nargs='+',
    help='Execute this command, and re-execute it whenever it dies.')
  parser.add_argument('-l', '--log', type=argparse.FileType('a'),
    help='Write stats on the process to this file. Each line is 3 tab-delimited columns: unix time '
         'the process died, number of seconds it ran, and its exit code.')
  parser.add_argument('-k', '--key',
    help='Output this string as column 4 in the stats log output.')
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

  start = time.time()
  now = None
  while True:
    if now is None:
      logging.info('Info: Launching command..')
    else:
      logging.info('Info: Restarting..')
    result = subprocess.run(args.command)
    if args.error_log:
      now = time.time()
      args.error_log.write(format_log_line(start, now, result, args.key))
      start = now


def format_log_line(start, now, result, key):
  elapsed_float = now-start
  elapsed_rounded = round(elapsed_float, 1)
  elapsed_int = int(elapsed_float)
  if elapsed_rounded == elapsed_int:
    elapsed = elapsed_int
  else:
    elapsed = elapsed_rounded
  fields = [int(now), elapsed, result.returncode]
  if key is not None:
    fields.append(key)
  logging.info('Info: Process exited in {} seconds with code {}.'.format(elapsed, result.returncode))
  return '\t'.join(map(str, fields))+'\n'


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
