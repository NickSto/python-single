#!/usr/bin/env python3
import argparse
import collections
import logging
import math
import sys
from utillib import console
assert sys.version_info.major >= 3, 'Python 3 required'

DEFAULT_TRUNCATED_COLUMNS = (-1, 0)
DESCRIPTION = """Adjust column spacing to fit the width."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('input', default=sys.stdin, type=argparse.FileType('r'), nargs='?',
    help='Input file. Default: stdin.')
  parser.add_argument('-t', '--truncated-columns', type=int_list, default=DEFAULT_TRUNCATED_COLUMNS,
    help='Columns to truncate if the output is too wide. Give as a comma-separated list of 0-based '
         'column indices. Default: %(default)s')
  parser.add_argument('-s', '--start', dest='trunc_from', action='store_const', const='start',
    default='end',
    help='When truncating columns, remove from the start instead of the end.')
  parser.add_argument('-e', '--expand', action='store_true',
    help='Expand the columns to fill the current terminal width.')
  parser.add_argument('-i', '--include-all-columns', dest='omit_cols', action='store_false',
    default=True,
    help='Default behavior is to only print the columns shared by all lines. This option includes '
         'every column instead.')
  parser.add_argument('-x', '--exclude', action='append',
    help='Exclude lines with this value. Use this option multiple times to specify multiple '
         'filters. Any line where a field matches this string (exactly) will be excluded. You can '
         'also give two arguments separated by commas. The first argument can be a number (1-based) '
         'specifying that only a certain column is to be matched. Or, the first argument can be a '
         'keyword telling whether to do an exact match ("exact"), match anywhere inside the field '
         '("contains"), at the start of the field ("start"), or end ("end"). The second argument '
         'should be the string to match. There is also a 3-argument form, where the first argument '
         'is the column number, the second is the match type, and the third is the match string.')
  parser.add_argument('-w', '--term-width', type=int, default=console.termwidth(),
    help='Force the script to think the terminal width is this, instead of auto-detecting it.')
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

  excludes = parse_excludes(args.exclude)

  lines, max_width = parse_input(args.input)

  excludes_columned, excludes_uncolumned = collate_excludes(excludes)
  lines = filter_lines(lines, excludes_columned, excludes_uncolumned)

  max_widths = get_max_column_widths(lines, omit_cols=args.omit_cols)

  if args.expand:
    max_width = args.term_width
  else:
    max_width = min(args.term_width, max_width)

  widths = calculate_column_widths(max_width, max_widths, args.truncated_columns)

  print_lines(lines, widths, omit_cols=args.omit_cols, trunc_from=args.trunc_from)


def parse_excludes(exclude_list):
  excludes = []
  if exclude_list is None:
    return excludes
  valid_match_types = {'exact', 'contains', 'start', 'end'}
  for filter_str in exclude_list:
    fields = filter_str.split(',')
    if len(fields) == 1:
      exclude = {'match':'exact', 'column':'any', 'string':fields[0]}
    elif len(fields) == 2:
      try:
        column = int(fields[0])-1
        match = 'exact'
      except ValueError:
        column = 'any'
        match = fields[0]
      if match not in valid_match_types:
        logging.warning(f'Warning: Invalid --exclude match type {match!r}')
        continue
      exclude = {'match':match, 'column':column, 'string':fields[1]}
    elif len(fields) == 3:
      try:
        column = int(fields[0])-1
      except ValueError:
        logging.warning(f'Warning: Invalid --exclude column {fields[0]!r}')
        continue
      exclude = {'match':fields[1], 'column':column, 'string':fields[2]}
    excludes.append(exclude)
  return excludes


def collate_excludes(excludes):
  excludes_uncolumned = collections.defaultdict(set)
  excludes_columned = collections.defaultdict(lambda: collections.defaultdict(set))
  for exclude in excludes:
    if exclude['column'] == 'any':
      excludes_uncolumned[exclude['match']].add(exclude['string'])
    else:
      excludes_columned[exclude['column']][exclude['match']].add(exclude['string'])
  return excludes_columned, excludes_uncolumned


def filter_lines(lines, excludes_columned, excludes_uncolumned):
  filtered_lines = []
  for i, line in enumerate(lines):
    if filter_line(line, excludes_columned, excludes_uncolumned):
      logging.info(f'Excluding line {i+1}..')
    else:
      filtered_lines.append(line)
  return filtered_lines


def filter_line(line, excludes_columned, excludes_uncolumned):
  for i, field in enumerate(line):
    if match_field(field, excludes_uncolumned):
      return True
    elif i in excludes_columned and match_field(field, excludes_columned[i]):
      return True
  return False


def match_field(value, queries):
  for match_type, strings in queries.items():
    if match_type == 'exact':
      if value in strings:
        logging.debug(f'Field {value!r} matches "exact" filter.')
        return True
    elif match_type == 'contains':
      for string in strings:
        if string in value:
          logging.debug(f'Field {value!r} matches "contains" filter {string!r}.')
          return True
    elif match_type == 'start':
      for string in strings:
        if value.startswith(string):
          logging.debug(f'Field {value!r} matches "start" filter {string!r}.')
          return True
    elif match_type == 'end':
      for string in strings:
        if value.endswith(string):
          logging.debug(f'Field {value!r} matches "end" filter {string!r}.')
          return True
  return False


def parse_input(input_file):
  lines = []
  max_width = 0
  for line_raw in input_file:
    line = line_raw.rstrip('\r\n')
    max_width = max(len(line), max_width)
    if line:
      lines.append(line.split())
  return lines, max_width


def get_max_column_widths(lines, omit_cols=False):
  widths = []
  min_num_columns = 999999999
  for line in lines:
    min_num_columns = min(len(line), min_num_columns)
    for i, field in enumerate(line):
      if len(widths) <= i:
        widths.append(len(field))
      else:
        widths[i] = max(len(field), widths[i])
  if omit_cols:
    widths = widths[:min_num_columns]
  return widths


def calculate_column_widths(max_width, max_widths, truncated_columns):
  # The starting widths are the maximum width of the strings in each column, plus 1 for a space.
  widths = [width+1 for width in max_widths]
  # But subtract 1 from the last column because we don't need a space there.
  widths[-1] -= 1
  widths_total = sum(widths)
  free_space = max_width - widths_total
  if free_space < 0:
    remove_per_column = -free_space / len(truncated_columns)
    logging.debug(f'Removing {remove_per_column} from columns {truncated_columns}')
    for i in truncated_columns:
      decrease = min(math.ceil(remove_per_column), sum(widths) - max_width)
      widths[i] -= decrease
      if sum(widths) <= max_width:
        break
  else:
    free_space_per_column = free_space / (len(widths)-1)
    for i, width in enumerate(widths[:-1]):
      increase = min(math.ceil(free_space_per_column), max_width - sum(widths))
      # print(f'Adding {increase} to {width} (column {i})')
      widths[i] += increase
      if sum(widths) >= max_width:
        break
  logging.info(f'Calculated widths: {widths}')
  return widths


def print_lines(lines, widths, omit_cols=True, trunc_from='end'):
  logging.info(f'trunc_from: {trunc_from}')
  for line in lines:
    for i, field in enumerate(line):
      if omit_cols and i >= len(widths):
        print()
      else:
        start = max(0, len(field)+1 - widths[i])
        end = widths[i] - 1
        if i+1 == len(line):
          start = max(0, start-1)
          end += 1
        if trunc_from == 'start':
          final_field = field[start:]
        else:
          final_field = field[:end]
        spaces = widths[i] - len(final_field)
        if i+1 == len(line):
          ending = '\n'
        else:
          ending = ' ' * spaces
        sys.stdout.write(final_field + ending)


def int_list(csv):
  int_strs = csv.split(',')
  return [int(int_str) for int_str in int_strs]


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
