#!/usr/bin/env python3
import os
import sys
import time
import shutil
import logging
import argparse
import datetime
assert sys.version_info.major >= 3, 'Python 3 required'

VERSION = 2.0
NOW = int(time.time())
PERIODS = {
  # 'minutely': 60,
  'hourly': 60*60,
  'daily':  24*60*60,
  'weekly': 7*24*60*60,
  'monthly':int(60*60*24*365.2425/12),
  'yearly': int(60*60*24*365.2425),
  'forever':NOW-1,
}
DESCRIPTION = """Archive copies of the target file. Keep a set of copies from different time
periods, like the last hour, day, week, month, etc."""


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('file',
    help='The file to back up.')
  parser.add_argument('-g', '--group-name',
    help='Use this option when the filename varies. All copies will be organized under this name '
         "and considered different versions of the same file. Files won't be renamed when "
         'archived, so they must have unique filenames.')
  parser.add_argument('-n', '--new', action='store_true',
    help="This is a new file (hasn't been archived before).")
  parser.add_argument('-d', '--destination',
    help='The directory the archive is/should be stored in. Default is the same directory the '
         'target file lives in.')
  parser.add_argument('-a', '--archive-tracker')
  parser.add_argument('-e', '--ext',
    help='The extension of the file. You can use this to make sure the names of the archive files '
         'are like "example-2017-03-23-121700.tar.gz" instead of '
         '"example.tar-2017-03-23-121700.gz".')
  parser.add_argument('-c', '--copies', type=int, default=2,
    help='How many copies to keep per time period. Default: %(default)s')
  parser.add_argument('-m', '--min-size', type=int,
    help='Minimum file size (in bytes). If the target file is smaller than this, do not copy it '
         'into the archive.')
  parser.add_argument('--now', type=int, default=NOW,
    help='The unix timestamp to use as "now". For debugging.')
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
  tone_down_logger()

  # Check the input paths exist.
  if not os.path.isfile(args.file):
    fail('Error: Target file {!r} not found.'.format(args.file))
  if args.destination and not os.path.isdir(args.destination):
    fail('Error: --destination {!r} not found.'.format(args.destination))

  if args.min_size and os.path.getsize(args.file) < args.min_size:
    fail('Error: Target file {!r} smaller than --min-size ({} < {})'
         .format(args.file, os.path.getsize(args.file), args.min_size))

  group_name = args.group_name or os.path.basename(args.file)
  destination = args.destination or os.path.dirname(args.file)
  archive_tracker = args.archive_tracker or os.path.join(destination, '.archive-tracker')

  # Read the tracker file, get the section on our target file.
  if os.path.isfile(archive_tracker):
    with open(archive_tracker) as tracker_file:
      tracker = read_tracker(tracker_file, periods=PERIODS, expected_version=VERSION)
  elif args.new:
    tracker_section = {}
    tracker = {group_name:tracker_section}
  else:
    fail(
      f"Tracker not found at {archive_tracker}. If this is a new file which hasn't been archived "
      'yet, use --new.'
    )
  try:
    tracker_section = tracker[group_name]
  except KeyError:
    if args.new:
      tracker_section = {}
      tracker[group_name] = tracker_section
    else:
      fail(
        f'Error: Target file/group "{group_name}" not found in tracker {archive_tracker}. If this '
        "is a new file which hasn't been archived yet, use --new."
      )

  # Determine which actions are needed.
  new_tracker_section, wanted = get_plan(tracker_section, destination, args.copies, periods=PERIODS,
                                         now=args.now)

  # If new archives are needed, copy the target file to use as a new archive file, and update the
  # tracker with its path.
  if wanted:
    if args.group_name:
      archive_file_path = args.file
    else:
      archive_file_path = get_archive_path(args.file, destination, args.ext, now=args.now)
      logging.info(f'Copying target file {args.file} to {archive_file_path}')
      shutil.copy2(args.file, archive_file_path)
    add_new_file(new_tracker_section, wanted, archive_file_path, now=args.now)

  # Delete the now-unneeded archive files.
  files_to_delete = get_files_to_delete(tracker_section, new_tracker_section)
  delete_files(files_to_delete, destination)

  # Write the updated tracker file.
  tracker[group_name] = new_tracker_section
  write_tracker(tracker, archive_tracker, periods=PERIODS, version=VERSION)


def read_tracker(tracker_file, periods=PERIODS, expected_version=VERSION):
  """
  Tracker file format (tab-delimited):
    >version=1.0
    filename.ext
        monthly   1   1380426100    filename-2013-09-28.ext
        monthly   2   1376366288    filename-2013-08-12.ext
        weekly    2   1380436173    filename-2013-09-29.ext
  Returned data structure:
    {
      'filename.ext': {
        'monthly': [
                     {'timestamp':1380426100, 'file':'filename-2013-09-28.ext'},
                     {'timestamp':1376366288, 'file':'filename-2013-08-12.ext'}
                   ],
        'weekly':  [
                     None,
                     {'timestamp':1380436173, 'file':'filename-2013-09-17.ext'}
                   ]
      }
    }
  "filename.ext" begins one section, and there can be many sections in one file.
  """
  version = None
  tracker = {}
  section = {}
  path = None
  for line_raw in tracker_file:
    # What kind of line is it?
    header = line_raw.startswith('>')
    section_header = not line_raw.startswith('\t')
    line = line_raw.strip()
    # Ignore empty lines.
    if not line:
      continue
    # Check version in header.
    if header:
      if line.startswith('>version='):
        version = float(line[9:])
        if version > expected_version or expected_version - version >= 1.0:
          fail('Error: tracker file is version {}, which is incompatible with the current version '
               '{}'.format(version, expected_version))
      continue
    # Start a new section.
    if section_header:
      if not version:
        fail('Error: no version specified in tracker file.')
      if section and path:
        tracker[path] = section
      section = {}
      path = line
    else:
      # Parse a data line.
      fields = line.split('\t')
      if len(fields) == 4:
        period = fields[0].lower()
        copy = fields[1]
        timestamp = fields[2]
        filename = fields[3]
      else:
        fail('Error in tracker file. Wrong number of fields ({}) on line\n{}'
             .format(len(fields), line_raw))
      if period not in periods:
        fail('Error in tracker file. Invalid period "{}" on line\n{}'.format(period, line))
      try:
        timestamp = int(timestamp)
      except ValueError:
        fail('Error in tracker file. Invalid timestamp {!r} on line\n{}'.format(timestamp, line))
      try:
        copy = int(copy)
      except ValueError:
        fail('Error in tracker file. Invalid copy number {!r} on line\n{}'.format(copy, line))
      if copy > 2000:
        fail('Error in tracker file. Copy too large ({}) on line\n{}'.format(copy, line))
      # Place the record for this line in the list for the period, at a location according to its
      # copy number.
      copies = section.get(period, [])
      while len(copies) < copy:
        copies.append(None)
      copies[copy-1] = {'timestamp':timestamp, 'file':filename}
      section[period] = copies
  # Save the last section.
  if section and path:
    tracker[path] = section
  return tracker


def get_plan(tracker_section, destination, required_copies, periods=PERIODS, now=NOW):
  """Determine the changes needed to update the archives.
  Returns:
  new_tracker_section: An updated tracker section with copies shifted and copy lists extended
    where necessary. The original tracker section is not altered.
  wanted: Missing archives that need to be created. Each element is a dict with the keys 'period'
    and 'copy'."""
  new_tracker_section = {}
  wanted = []
  all_archives = []
  # Pool all existing archives.
  for period in periods:
    for archive in tracker_section.get(period, []):
      if archive not in all_archives:
        all_archives.append(archive)
  for period in get_ordered_periods(periods):
    copies = []
    # Iterate through each time period, finding which archives are now within that period.
    # Choose one for each period (or None, if none exist).
    period_length = periods[period]
    for i, slot_start_age in enumerate(range(0, period_length*required_copies, period_length)):
      # Figure out the boundaries of this time slot.
      slot_end_age = slot_start_age + period_length
      slot_end = now - slot_start_age
      slot_start = now - slot_end_age
      candidates = []
      for archive in all_archives:
        # Check that the archive falls within the time period.
        if archive is not None and slot_start < archive['timestamp'] <= slot_end:
          # Check that the archive's file exists.
          path = os.path.join(destination, archive['file'])
          if os.path.isfile(path):
            candidates.append(archive)
          else:
            logging.warning('{} archive is missing (file {!r}).'.format(period, path))
      if candidates:
        # Choose the oldest archive, if there are multiple.
        candidates.sort(key=lambda archive: archive['timestamp'])
        copies.append(candidates[0].copy())
      else:
        logging.debug('No existing archive can serve as {} copy {}.'.format(period, i+1))
        if i+1 == 1:
          # Add it to the wanted list if it's copy 1.
          # If it's not copy 1, then making a new backup and calling it copy 2, for example, would
          # end up with a copy 2 younger than copy 1. Or, if we don't have a copy 1 already, we'll
          # be getting one shortly, which will end up being the same file as this copy 2 anyway.
          wanted.append({'period':period, 'copy':i+1})
        copies.append(None)
    new_tracker_section[period] = copies
  return new_tracker_section, wanted


def get_archive_path(target_path, destination, ext=None, now=NOW):
  filename = os.path.basename(target_path)
  if ext is None:
    base, ext = os.path.splitext(filename)
  else:
    if not ext.startswith('.'):
      ext = '.'+ext
    if filename.endswith(ext):
      base = filename[:-len(ext)]
  time_str = datetime.datetime.fromtimestamp(now).strftime('%Y-%m-%d-%H%M%S')
  archive_filename = base+'-'+time_str+ext
  return os.path.join(destination, archive_filename)


def add_new_file(tracker_section, wanted, archive_file_path, now=NOW):
  """Add the path for a new archive file to the tracker, in the places indicated by the wanted list.
  """
  logging.info('Saving as '+', '.join(['{period} copy {copy}'.format(**w) for w in wanted]))
  filename = os.path.basename(archive_file_path)
  for wanted_archive in wanted:
    period = wanted_archive['period']
    copy = wanted_archive['copy']
    copies = tracker_section.get(period, [])
    while len(copies) < copy:
      copies.append(None)
    copies[copy-1] = {'timestamp':now, 'file':filename}
    tracker_section[period] = copies


def get_files_to_delete(tracker_section, new_tracker_section):
  old_files = get_files_in_tracker_section(tracker_section)
  new_files = get_files_in_tracker_section(new_tracker_section)
  return old_files - new_files


def get_files_in_tracker_section(tracker_section):
  files = set()
  for period, copies in tracker_section.items():
    for archive in copies:
      if archive is not None:
        files.add(archive['file'])
  return files


def delete_files(files_to_delete, destination):
  if files_to_delete:
    logging.info('Deleting old archive files: "'+'", "'.join(files_to_delete)+'"')
  for filename in files_to_delete:
    path = os.path.join(destination, filename)
    if os.path.isfile(path):
      logging.debug('Deleting old archive file {!r}'.format(filename))
      try:
        os.remove(path)
      except OSError:
        fail('Error: Could not delete file {!r}.'.format(path))
    else:
      logging.warning('Warning: Could not find file {!r}'.format(path))


def get_ordered_periods(periods=PERIODS):
  ordered_periods = []
  for period, age in sorted(periods.items(), key=lambda i: i[1]):
    ordered_periods.append(period)
  return ordered_periods


def write_tracker(tracker, tracker_path, periods=PERIODS, version=VERSION):
  ordered_periods = get_ordered_periods(periods)
  try:
    with open(tracker_path, 'w') as tracker_file:
      tracker_file.write('>version={}\n'.format(version))
      for path, section in tracker.items():
        tracker_file.write(path+'\n')
        for period in ordered_periods:
          copies = section.get(period, [])
          for i, archive in enumerate(copies):
            if archive is not None:
              tracker_file.write('\t{}\t{}\t{timestamp}\t{file}\n'.format(period, i+1, **archive))
  except IOError:
    fail('Could not open file {!r}'.format(tracker_path))


def tone_down_logger():
  """Change the logging level names from all-caps to capitalized lowercase.
  E.g. "WARNING" -> "Warning" (turn down the volume a bit in your log files)"""
  for level in (logging.CRITICAL, logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG):
    level_name = logging.getLevelName(level)
    logging.addLevelName(level, level_name.capitalize())


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
