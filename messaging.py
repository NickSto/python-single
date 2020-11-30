#!/usr/bin/env python3
import logging
import os
import pathlib


PROC_ROOT = pathlib.Path('/proc')

def send_signals(process_names, signal):
  if not process_names or signal is None:
    return
  for pid, argv in list_processes():
    if match_cmdline(argv, process_names):
      logging.info('Info: Found process {}: {}'.format(pid, ' '.join(argv)))
      os.kill(pid, signal)


def find_processes(query):
  for pid, argv in list_processes():
    if match_cmdline(argv, query):
      yield pid


def list_processes():
  """Generate a list of pids and command lines of running processes."""
  for proc_dir in PROC_ROOT.iterdir():
    if not (proc_dir.name.isdigit() and proc_dir.is_dir()):
      continue
    cmdline_path = proc_dir/'cmdline'
    if not cmdline_path.is_file():
      continue
    try:
      cmdline_bytes = cmdline_path.open('rb').read()
    except IOError:
      # Process ended before we got to read it.
      continue
    argv = [str(arg, 'utf8') for arg in cmdline_bytes.split(b'\0')]
    yield int(proc_dir.name), argv[:-1]


def match_cmdline(argv, queries):
  """Return true if a given command line matches a set of queries.
  A query matches if it's identical to the basename of the $0 argument (the command) or the $1
  argument."""
  if not argv:
    return False
  cmd = os.path.basename(argv[0])
  if cmd in queries:
    return True
  elif len(argv) > 1:
    script = os.path.basename(argv[1])
    if script in queries:
      return True
  return False


def get_environ_vars(pid):
  variables = {}
  environ_path = PROC_ROOT/f'{pid}/environ'
  if not environ_path.is_file():
    logging.info(f'Info: Process {pid} environment not found.')
    return None
  try:
    environ_bytes = environ_path.open('rb').read()
  except IOError:
    # Process ended before we got to read it, or we don't have enough permissions.
    logging.info(f'Info: Process {pid} environment not readable.')
    return None
  if len(environ_bytes) == 0:
    return variables
  for line_bytes in environ_bytes.split(b'\0'):
    line = str(line_bytes, 'utf8')
    if line == '':
      continue
    fields = line.split('=')
    if len(fields) < 2:
      logging.info(f'Info: Malformed environment variable definition in {environ_path}: {line!r}')
      continue
    variables[fields[0]] = '='.join(fields[1:])
  return variables
