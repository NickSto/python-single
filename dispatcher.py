#!/usr/bin/env python3
import argparse
import logging
import pathlib
import sys
assert sys.version_info.major >= 3, 'Python 3 required'

DESCRIPTION = """Take actions based on the content of a simple input file."""


def make_argparser():
  parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
  options = parser.add_argument_group('Options')
  options.add_argument('infile', type=argparse.FileType('r'), default=sys.stdin, nargs='?',
    help='Input file. Omit to read from stdin.')
  options.add_argument('-h', '--help', action='help',
    help='Print this argument help text and exit.')
  logs = parser.add_argument_group('Logging')
  logs.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = logs.add_mutually_exclusive_group()
  volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  for lines in chunk_input(args.infile):
    command, args = parse_command(lines[0])
    content = lines[1:]
    try:
      fxn = COMMANDS[command]
    except KeyError:
      logging.error(f'Error: Unrecognized command {command!r} in line {lines[0]!r}')
    else:
      fxn(args, content)


def chunk_input(lines):
  chunk_lines = []
  for line_raw in lines:
    line = line_raw.rstrip('\r\n')
    if line.startswith('#!'):
      if chunk_lines:
        yield chunk_lines
      chunk_lines = []
    chunk_lines.append(line)
  if chunk_lines:
    yield chunk_lines


def parse_command(command_line):
  assert command_line.startswith('#!'), command_line
  fields = command_line[2:].split()
  command = fields[0]
  args = fields[1:]
  return command, args


def do_cat(args, content):
  for path in [pathlib.Path(arg) for arg in args]:
    if not path.parent.is_dir():
      logging.error(f'Error: Directory containing {str(path)!r} not found.')
      continue
    try:
      with path.open('w') as file:
        for line in content:
          print(line, file=file)
    except OSError as error:
      logging.error(f'Error: Failed writing to file {str(path)!r}: {error}')


COMMANDS = {
  'cat':do_cat,
}


def fail(message):
  logging.critical('Error: '+str(message))
  if __name__ == '__main__':
    sys.exit(1)
  else:
    raise Exception(message)


if __name__ == '__main__':
  try:
    sys.exit(main(sys.argv))
  except BrokenPipeError:
    pass
