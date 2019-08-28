#!/usr/bin/env python3
import argparse
import sys
import urllib.parse


USAGE = "%(prog)s [options]"
DESCRIPTION = """Percent-encode and decode strings (like in a URL).
This is a thin wrapper around urllib.parse.quote() and urllib.parse.unquote()."""

def main(argv):

  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('operation', choices=('encode', 'decode'),
    help='Whether to "encode" or "decode".')
  parser.add_argument('string', nargs='?',
    help='The string to encode or decode. Omit to read from stdin.')
  parser.add_argument('-p', '--preserve', default='',
    help='Preserve these characters instead of encoding them. This is in addition to the default '
         'preserved characters (letters, numbers, "_", ".", and "-").')

  args = parser.parse_args(argv[1:])

  if args.string:
    lines = [args.string]
  else:
    lines = sys.stdin

  if args.operation == 'encode':
    for line in lines:
      print(urllib.parse.quote(line, safe=args.preserve), end='')
  elif args.operation == 'decode':
    for line in lines:
      print(urllib.parse.unquote(line), end='')
  else:
    raise AssertionError('Operation must be "encode" or "decode".')
  print()


if __name__ == '__main__':
  sys.exit(main(sys.argv))
