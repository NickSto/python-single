#!/usr/bin/env python3
import argparse
import logging
import os
import pathlib
import sys
try:
  import yaml
except ImportError:
  yaml = None
assert sys.version_info.major >= 3, 'Python 3 required'

HOME = pathlib.Path('~').expanduser()
HEXCHARS = set('0123456789abcdef')
EXCLUDED_TEMPLATE = {'exact':[], 'dirs':[], 'relative_dirs':[]}
EXCLUDED_BASIC = EXCLUDED_TEMPLATE.copy()
EXCLUDED_BASIC['dirs'] = (str(HOME/'.config/google-chrome'), str(HOME/'.local/share/nbsdata'))
DESCRIPTION = """Parse and filter CrashPlan's backup logs."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('log', metavar='backup_files.log.0', type=argparse.FileType('r'),
    help='Crashplan backup log. Standard location: /usr/local/crashplan/log. Or it might be in '
         '~/src/crashplan/log.')
  parser.add_argument('-p', '--path', action='store_true',
    help='Just print the paths of the changed/deleted files.')
  parser.add_argument('-d', '--start-date',
    help='Only print entries on or after this date. String must match the one in the file exactly.')
  parser.add_argument('-x', '--exclude', metavar='exclude.yaml', type=argparse.FileType('r'),
    help='Exclude paths fitting the filter criteria in this yaml file.')
  parser.add_argument('-e', '--exclude-basic', action='store_true',
    help='Exclude some paths that appear very frequently, instead of providing a full filter list '
         'with --exclude.')
  parser.add_argument('-l', '--error-log', type=argparse.FileType('w'), default=sys.stderr,
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

  if args.exclude_basic:
    excluded = EXCLUDED_BASIC
  elif args.exclude:
    excluded = parse_excluded(args.exclude)
  else:
    excluded = EXCLUDED_TEMPLATE.copy()

  if args.start_date:
    started = False
  else:
    started = True
  for line in args.log:
    entry = parse_line(line)
    if not started and entry['date'] == args.start_date:
      started = True
    if (started and
        (entry['hash'] and entry['num2'] is not None) and
        (entry['result'] != 'I' or entry['deleted'] or entry['stats'].get('bytes')) and
        not exclude_path(entry['path'], excluded)):
      if args.path:
        print(entry['path'])
      else:
        print('{date} {time}: {path}'.format(**entry))


def parse_excluded(excluded_file):
  if yaml is None:
    fail('Error: yaml module required to parse excluded file.')
  excluded = EXCLUDED_TEMPLATE.copy()
  excluded_data = yaml.safe_load(excluded_file)
  home = pathlib.Path('~').expanduser()
  home_relative = excluded_data.get('home_relative', {})
  for path in home_relative.get('dirs', ()):
    dirpath = path.rstrip('/')+'/'
    excluded['dirs'].append(str(home/dirpath))
  for path in home_relative.get('exact', ()):
    excluded['exact'].append(str(home/path))
  absolute = excluded_data.get('absolute', {})
  for path in absolute.get('dirs', ()):
    dirpath = path.rstrip('/')+'/'
    excluded['dirs'].append(dirpath)
  for path in absolute.get('exact', ()):
    excluded['exact'].append(path)
  relative = excluded_data.get('relative', {})
  for path in relative.get('dirs', ()):
    excluded['relative_dirs'].append(path)
  return excluded


def exclude_path(path, excluded):
  for dirpath in excluded['dirs']:
    if path.startswith(dirpath):
      return True
  for exact in excluded['exact']:
    if path == exact:
      return True
  for relative_dir in excluded['relative_dirs']:
    for dir in path.split(os.sep)[:-1]:
      if dir == relative_dir:
        return True
  return False


def parse_line(line):
  fields = line.rstrip('\r\n').split(' ')
  # Field 4
  num1 = int(fields[3])
  # Field 5: File hash(?)
  digest = fields[4]
  if len(digest) != 32 or set(digest) - HEXCHARS:
    digest = None
  try:
    num2 = int(fields[5])
  except ValueError:
    num2 = None
  # Field 6: File path
  prefix = ' '.join(fields[:6])
  postfix = ' '.join(fields[-2:])
  path = line[len(prefix)+1:-len(postfix)-2]
  # Field 8: Stats array
  stats_str = fields[-1]
  if stats_str.startswith('[') and stats_str.endswith(']'):
    stats_fields = stats_str[1:-1].split(',')
    if len(stats_fields) == 7:
      stats = {'changed':stats_fields[0], 'unchanged':stats_fields[1], 'bytes':stats_fields[2]}
      for i in 4, 5, 6, 7:
        stats[i] = stats_fields[i-1]
    else:
      stats = {}
      logging.warning('Warning: Wrong number of fields in stats: {!r}'.format(stats_str))
  else:
    stats = {}
  # Field 7: Filesize
  paren_str = fields[-2]
  deleted = False
  size = None
  if stats and paren_str.startswith('(') and paren_str.endswith(')'):
    try:
      size = int(paren_str[1:-1])
    except ValueError:
      if paren_str[1:-1] == 'deleted':
        deleted = True
      else:
        raise ValueError('Parenthetical unrecognized: {!r}'.format(paren_str))
  else:
    paren = None
  return {'result':fields[0], 'date':fields[1], 'time':fields[2], 'num1':num1, 'hash':digest,
          'num2':num2, 'path':path, 'stats':stats, 'size':size, 'deleted':deleted}


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
