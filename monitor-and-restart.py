#!/usr/bin/env python3
import argparse
import logging
import signal
import subprocess
import sys
import time
assert sys.version_info.major >= 3, 'Python 3 required'

# Incoming IPC signals.
INBOX = []

DESCRIPTION = """Launch a process, keep it running, and log statistics on its uptime. This is
basically run-one-constantly, but with stats logging."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('command', nargs='+',
    help='Execute this command, and re-execute it whenever it dies.')
  parser.add_argument('-t', '--timeout', type=int,
    help='Automatically kill and restart the command after this many seconds.')
  parser.add_argument('-l', '--log', type=argparse.FileType('a'),
    help='Write stats on the process to this file. Each line is 4 tab-delimited columns: unix time '
         'the process died, number of seconds it ran, its exit code, and the reason for it dying. '
         'A reason of "exited" means the process exited on its own. A reason of "timeout" means '
         'it reached the timeout and was killed by this script.')
  parser.add_argument('-k', '--key',
    help='Output this string as column 4 in the stats log output.')
  parser.add_argument('-p', '--pause', type=float, default=0.2,
    help='Seconds to wait between polling for whether the process is still alive.')
  parser.add_argument('-L', '--error-log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING,
    help='Silence all but the most critical errors. Also silence stderr from the subprocess.')
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.error_log, level=args.volume, format='%(message)s')

  for signum in signal.SIGCONT, signal.SIGPWR, signal.SIGUSR1, signal.SIGUSR2:
    signal.signal(signum, signal_handler)

  start = time.time()
  now = None
  while True:
    if now is None:
      logging.info('Info: Launching command..')
    else:
      logging.info('Info: Restarting..')
    # Run the process and wait for it to exit (or timeout).
    if logging.getLogger().getEffectiveLevel() >= logging.CRITICAL:
      stderr = subprocess.DEVNULL
    else:
      stderr = None
    process = subprocess.Popen(args.command, stderr=stderr)
    try:
      retval, reason = run_until(process, args.timeout, start, args.pause)
    except KeyboardInterrupt:
      kill_process(process, args.pause, wait=False)
      return
    # If it didn't exit and we decided to kill it, kill it.
    if retval is None:
      kill_process(process, args.pause, wait=True)
    now = time.time()
    # Record stats.
    if args.log:
      args.log.write(format_log_line(args.key, now, start, retval, reason))
    start = now


def run_until(process, timeout, start, pause):
  """Monitor the process and return when it finishes (dies or times out)."""
  reason = 'exited'
  retval = process.poll()
  while retval is None:
    time.sleep(pause)
    if timeout:
      elapsed = time.time() - start
      if elapsed > timeout:
        reason = 'timeout'
        logging.info('Info: Process timed out.')
    while INBOX:
      signalnum, timestamp = INBOX.pop(0)
      if signalnum == signal.SIGCONT:
        reason = 'wakeup'
        logging.info('Info: System resumed from sleep.')
      elif signalnum == signal.SIGUSR2:
        reason = 'unlock'
        logging.info('Info: Screen unlocked.')
    if reason in ('timeout', 'wakeup', 'unlock'):
      break
    retval = process.poll()
  return retval, reason


def kill_process(process, pause, wait=False):
  process.terminate()
  start = time.time()
  tries = 0
  while process.poll() is None:
    if tries > 0:
      if wait:
        now = time.time()
        logging.warning('Warning: Process won\'t die after {} tries and {:0.1f} seconds.'
                        .format(tries, now - start))
      else:
        fail('Error: Process won\'t die!')
    process.terminate()
    time.sleep(pause)
    if process.poll() is not None:
      return
    process.kill()
    time.sleep(pause)
    pause = pause * 2
    tries += 1


def signal_handler(signalnum, frame):
  """Log receipt of signals for other parts of the script to inspect."""
  INBOX.append((signalnum, time.time()))


def format_log_line(key, now, start, retval, reason):
  elapsed_float = now-start
  elapsed_rounded = round(elapsed_float, 1)
  elapsed_int = int(elapsed_float)
  if elapsed_rounded == elapsed_int or elapsed_int >= 100:
    elapsed = elapsed_int
  else:
    elapsed = elapsed_rounded
  fields = [int(now), elapsed, retval, reason]
  if key is not None:
    fields.append(key)
  if reason is 'exited':
    logging.info('Info: Process exited in {} with code {}.'
                 .format(human_time(elapsed), retval))
  else:
    logging.info('Info: Process ended in {} for reason {!r}.'
                 .format(human_time(elapsed), reason))
  return '\t'.join(map(str, fields))+'\n'


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
