#!/usr/bin/env python3
import argparse
import csv
import logging
import sys
from typing import Iterable, Literal, Optional, NoReturn, Sequence, Union

CSV_FORMAT = {'dialect':'unix', 'delimiter':'\t', 'quoting':csv.QUOTE_MINIMAL, 'strict':True}
DESCRIPTION = """Format a table into human-readable and markup formats."""

#TODO: Option to specify columns to align left or right. Use cut -f syntax.
#TODO: Correctly format Markdown and Jira tables without headers.

def make_argparser():
    parser = argparse.ArgumentParser(add_help=False, description=DESCRIPTION)
    options = parser.add_argument_group('Options')
    options.add_argument('table', metavar='table.tsv', type=argparse.FileType('r'), nargs='?',
        default=sys.stdin,
        help='A file containing the table to format. If not given, this will read it from stdin. '
        'Either way, the table should be in tab-separated format.')
    options.add_argument('-H', '--headers', type=int, default=1,
        help='The number of header rows at the top of the table. Or, if using --rotate, this is '
            'the number of columns at the left of the table that will be output as headers at the '
            'top. Default is %(default)s.')
    options.add_argument('-t', '--tsv', dest='format', action='store_const', const='tsv',
        default='simple',
        help='Print the output in tab-separated format instead of human-readable format.')
    options.add_argument('-m', '--markdown', dest='format', action='store_const', const='markdown',
        help='Print the output in markdown table format.')
    options.add_argument('-j', '--jira', dest='format', action='store_const', const='jira',
        help="Print the output in Jira's table format.")
    options.add_argument('-r', '--rotate', action='store_true',
        help='Rotate the output table so the rows become columns and vice versa.')
    options.add_argument('-S', '--shrink-wrap', dest='pad', action='store_false', default=True,
        help='When printing in text format, do not pad the cells with extra spaces.')
    options.add_argument('-N', '--not-numbers', dest='not_numbers', type=str,
        help='Columns that should not be treated as numbers (right-aligned, formatted with commas). '
            'Specify columns using 1-based `cut -f` syntax, e.g., "1,3-5".')
    options.add_argument('-h', '--help', action='help',
        help='Print this argument help text and exit.')
    logs = parser.add_argument_group('Logging')
    logs.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
        help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
    volume = logs.add_mutually_exclusive_group()
    volume.add_argument('-q', '--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
        default=logging.WARNING)
    volume.add_argument('-V', '--verbose', dest='volume', action='store_const', const=logging.INFO)
    volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
    return parser


def main(*argv: str) -> Optional[int]:

    parser = make_argparser()
    args = parser.parse_args(argv[1:])

    logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

    str_columns: set[int] = set()
    if args.not_numbers is not None:
        str_columns = parse_columns_spec(args.not_numbers)

    headers, body = parse_table(args.table, args.headers, args.rotate, str_columns)
    print_table(headers, body, output_format=args.format, pad=args.pad)

    return None

Value = str|int|float
Row = Sequence[Value]
RowSet = Sequence[Row]
Alignment = Literal["left","right",None]


def parse_columns_spec(spec: str) -> set[int]:
    columns: set[int] = set()
    for part in spec.split(','):
        if '-' in part:
            start, end = part.split('-', 1)
            columns.update(range(int(start), int(end) + 1))
        else:
            columns.add(int(part))
    return columns


def parse_table(
    lines: Iterable[str], num_headers: int, rotate: bool = False,
    str_columns: set[int] | None = None,
) -> tuple[list[list[Value]], list[list[Value]]]:
    headers: list[list[Value]] = []
    body: list[list[Value]] = []
    if str_columns is None:
        str_columns = set()
    for row_num, raw_row in enumerate(csv.reader(lines, **CSV_FORMAT), 1):
        row = []
        for col_num, raw_value in enumerate(raw_row, 1):
            if col_num in str_columns:
                value: Value = raw_value
            else:
                try:
                    value = int(raw_value)
                except ValueError:
                    try:
                        value = float(raw_value)
                    except ValueError:
                        value = raw_value
            row.append(value)
        if not rotate:
            if row_num <= num_headers:
                headers.append(row)
            else:
                body.append(row)
        elif row_num == 1:
            for col_num, value in enumerate(row, 1):
                if col_num <= num_headers:
                    headers.append([value])
                else:
                    body.append([value])
        else:
            for col_num, value in enumerate(row, 1):
                if col_num <= num_headers:
                    headers[col_num-1].append(value)
                else:
                    body[col_num-num_headers-1].append(value)
    return headers, body


def print_table(
    headers: Sequence[Sequence], body: Sequence[Sequence], output_format: Optional[str],
    pad: bool = True,
) -> None:
    if output_format == 'tsv':
        print_tsv(headers, body)
    elif output_format == 'markdown':
        print_markdown_table(headers, body, pad=pad)
    elif output_format == 'jira':
        print_jira_table(headers, body, pad=pad)
    elif output_format == 'simple':
        print_simple_table(headers, body)
    else:
        raise ValueError(f'Unknown output format: {output_format}')


def print_tsv(headers: Sequence[Sequence], body: Sequence[Sequence]) -> None:
    for row in list(headers) + list(body):
        print(*row, sep='\t')


def print_markdown_table(headers: RowSet, body: RowSet, pad: bool = True) -> None:
    for line in render_text_table(headers, body, '|', '|', pad=pad, header_sep=True):
        print(line)


def print_jira_table(headers: RowSet, body: RowSet, pad: bool = True) -> None:
    for line in render_text_table(headers, body, '||', '|', pad=pad):
        print(line)


def print_simple_table(headers: RowSet, body: RowSet) -> None:
    for line in render_text_table(headers, body, ' ', ' ', pad=False, edge_delims=False):
        print(line)


def render_text_table(
    headers: RowSet, body: RowSet, header_delim: str, body_delim: str, header_sep: bool = False,
    edge_delims: bool = True, pad: bool = True,
) -> list[str]:
    widths = get_column_widths(headers, body, len(header_delim), len(body_delim))
    lines = []
    # Render the header line.
    for header in headers:
        line = render_row(header, widths, header_delim, pad, edge_delims, is_header=True)
        lines.append(line)
    # Render the separator line if needed. Currently only applies to Markdown.
    if header_sep:
        alignments = get_alignments(body)
        line = render_separator(widths, body_delim, alignments, pad)
        lines.append(line)
    # Render the body lines.
    for row in body:
        line = render_row(row, widths, body_delim, pad, edge_delims)
        lines.append(line)
    return lines


def render_row(
    row: Row, widths: Sequence[int], delim: str, pad: bool, edge_delims: bool,
    is_header: bool = False,
) -> str:
    line = ''
    if edge_delims:
        line = delim
    for col, value in enumerate(row):
        width = widths[col] - len(delim)
        if pad:
            width += 1
        if is_header:
            str_value = str(value)
            if pad:
                cell = f'{str_value:^{width + 1}}'
            else:
                cell = f'{str_value:^{width}}'
        elif isinstance(value, str):
            cell = f'{value:<{width}}'
            if pad:
                cell = ' ' + cell
        else:
            cell = f'{value:>{width},}'
            if pad:
                cell += ' '
        line += cell
        if edge_delims or col < len(row) - 1:
            line += delim
    return line


def get_alignments(body: RowSet) -> list[Alignment]:
    alignments: list[Alignment] = []
    first_row = True
    for row in body:
        for col_num, value in enumerate(row):
            if isinstance(value, str):
                alignment: Alignment = 'left'
            else:
                alignment = 'right'
            if first_row:
                alignments.append(alignment)
            else:
                current = alignments[col_num]
                if current is not None and current != alignment:
                    #TODO: Do something more clever when there's disagreement.
                    #      I'm thinking right should override left. More important that numbers
                    #      be right-aligned. Also, I could provide a command line option.
                    alignment = None
                alignments[col_num] = alignment
        first_row = False
    return alignments


def render_separator(
    widths: Sequence[int], delim: str, alignments: Sequence[Alignment], pad: bool
) -> str:
    line = delim
    for col, width in enumerate(widths):
        alignment = alignments[col]
        width -= 1 + len(delim)
        if pad:
            width += 2
        cell = ''
        if alignment == 'left':
            cell += ':'
        cell += '-' * width
        if alignment == 'right':
            cell += ':'
        elif alignment is None:
            cell += '-'
        line += cell + delim
    return line


def get_column_widths(
    headers: RowSet, body: RowSet, header_delim_len: int = 1, body_delim_len: int = 1
) -> list[int]:
    widths = []
    first_row = True
    for section, rows in zip(('header', 'body'),(headers, body)):
        if section == 'header':
            delim_len = header_delim_len
        else:
            delim_len = body_delim_len
        for row in rows:
            for col_num, value in enumerate(row):
                if section == 'header':
                    value_width = len(str(value)) + delim_len
                else:
                    value_width = len(format_value(value)) + delim_len
                if first_row:
                    widths.append(value_width)
                else:
                    widths[col_num] = max(widths[col_num], value_width)
            first_row = False
    return widths


def format_value(value: str|int|float) -> str:
    if isinstance(value, (int, float)):
        return f'{value:,}'
    return str(value)


def fail(error: Union[str,BaseException], code: int = 1) -> NoReturn:
    if __name__ == '__main__':
        logging.critical(f'Error: {error}')
        sys.exit(code)
    elif isinstance(error, BaseException):
        raise error
    else:
        raise RuntimeError(error)


if __name__ == '__main__':
    try:
        sys.exit(main(*sys.argv))
    except BrokenPipeError:
        pass
