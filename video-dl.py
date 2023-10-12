#!/usr/bin/env python3
import argparse
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse
assert sys.version_info.major >= 3, 'Python 3 required'

# Downloading the "Save" playlists:
# - these will sit for a while looking like they're doing nothing, but that's because
#   (for some reason) youtube-dl takes a while download the playlist ids.
# $ "$HOME/bin/video-dl.py" --playlist --check-existing "$HOME/Videos/Youtube" --quality 360 --outdir "$HOME/Videos/Youtube/0nsorted/360" 'https://www.youtube.com/playlist?list=PLG3QUVI_eBaOYc-GaSKIX4iH8q_wjcLOk'
# $ "$HOME/bin/video-dl.py" --playlist --check-existing "$HOME/Videos/Youtube" --quality 720 --outdir "$HOME/Videos/Youtube/0nsorted/720" 'https://www.youtube.com/playlist?list=PLG3QUVI_eBaOV3xuHaltuqYuINP2pyuMB'

#TODO: WARC??
#      Looks like there's no WARC feature as of June 2020, though IA has requested the feature:
#      https://github.com/ytdl-org/youtube-dl/issues/21983
#      It seems what the Archive does currently is it uses youtube-dl --get-url to extract the
#      direct url to the Youtube video, then manually downloads with curl or wget.
#      Note: Currently, you get two video urls with this method. It seems one has the video, and
#      the other has the audio. Not sure if you can select different qualities.

DESCRIPTION = """Download and label a video using yt-dlp."""
YOUTUBE_DL_ARGS = ['--no-mtime', '--add-metadata', '--xattrs']
VALID_CONVERSIONS = ['mp3', 'm4a', 'flac', 'aac', 'wav']
SILENCE_PATH = pathlib.Path('~/.local/share/nbsdata/SILENCE').expanduser()
SUPPORTED_SITES = {
  'youtube': {
    'domain':'youtube.com',
    'base_url': 'https://www.youtube.com/watch?v={id}',
    'qualities': {
      '360':'18',
      '640':'18',
      '480':'135+250',  # 80k audio, 480p video (might not be available anymore)
      '720':'22', # This might've changed. At least for QDQo2lJht7Y, 22 is basically the same as 18.
      '1280':'22',
    },
  },
  'vimeo': {
    'domain':'vimeo.com'
  },
  'facebook': {
    'domain':'facebook.com',
    'qualities': {
      '360':'dash_sd_src',
      '640':'dash_sd_src',
      '18':'dash_sd_src',
      '720':'dash_hd_src',
      '1280':'dash_hd_src',
      '22':'dash_hd_src',
    }
  },
  'instagram': {
    'domain':'instagram.com'
  },
  'twitter': {
    'domain':'twitter.com'
  },
  'dailymotion': {
    'domain':'dailymotion.com'
  },
  'twitch': {
    'domain':'clips.twitch.tv'
  },
  'tiktok': {
    'domain':'tiktok.com'
  },
  'patreon': {
    'domain':'patreon.com',
    'qualities': {
      '360':'917',
      '480':'1240',
      '540':'1625',
      '720':'2493',
      '1080':'4712'
    }
  }
}


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('url',
    help='Video url.')
  parser.add_argument('title', nargs='?',
    help='Video title for filename.')
  parser.add_argument('-f', '--quality',
    help="Video quality to request. Will be passed on literally to youtube-dl unless it's a "
      'shorthand. Shorthands are available for '+get_qualities_str(SUPPORTED_SITES))
  parser.add_argument('-F', '--formats', action='store_true',
    help='Just fetch the available video quality options and print them.')
  parser.add_argument('-q', '--qualities', action='store_true',
    help='Just print the list of quality aliases for this site and what they map to.')
  parser.add_argument('-o', '--outdir', type=pathlib.Path, default=pathlib.Path('.'),
    help='Save the video to this directory.')
  parser.add_argument('-n', '--get-filename', action='store_true')
  parser.add_argument('-b', '--cookies', type=pathlib.Path,
    help='Netscape cookies file to pass to yt-dlp.')
  parser.add_argument('-c', '--convert-to', choices=VALID_CONVERSIONS,
    help='Give a file extension to convert the video to this audio format. The file will be named '
      '"{title}.{ext}".')
  parser.add_argument('-p', '--playlist', action='store_true',
    help='The url is for a playlist. Download all videos from it.')
  parser.add_argument('-C', '--check-existing', type=pathlib.Path,
    help='Check whether the video has already been downloaded by looking in this directory. '
      "If it's already been downloaded, skip it. Currently this only works for playlists. "
      'Note: This will check every subdirectory, recursively.')
  parser.add_argument('-P', '--posted',
    help='The string to insert into the [posted YYYYMMDD] field, if none can be automatically '
      'determined.')
  parser.add_argument('-Y', '--ytd', dest='exe', default='yt-dlp',
    action='store_const', const='youtube-dl',
    help='Use youtube-dl instead of yt-dlp.')
  parser.add_argument('-I', '--non-interactive', dest='interactive', default=True,
    action='store_const', const=False,
    help='Do not prompt the user for input. Proceed fully automatically.')
  parser.add_argument('-l', '--log', type=argparse.FileType('w'), default=sys.stderr,
    help='Print log messages to this file instead of to stderr. Warning: Will overwrite the file.')
  volume = parser.add_mutually_exclusive_group()
  volume.add_argument('--quiet', dest='volume', action='store_const', const=logging.CRITICAL,
    default=logging.WARNING)
  volume.add_argument('-v', '--verbose', dest='volume', action='store_const', const=logging.INFO)
  volume.add_argument('-D', '--debug', dest='volume', action='store_const', const=logging.DEBUG)
  return parser


def main(argv):

  parser = make_argparser()
  args = parser.parse_args(argv[1:])

  logging.basicConfig(stream=args.log, level=args.volume, format='%(message)s')

  if not shutil.which(args.exe):
    fail(f'Error: {args.exe!r} command not found.')

  if SILENCE_PATH.exists():
    fail(f'Error: Silence file exists: {str(SILENCE_PATH)!r}')

  if args.formats:
    cmd = (args.exe, '-F', args.url)
    logging.info(format_command(cmd))
    subprocess.run(cmd)
    return

  if args.qualities:
    site = get_site(args.url)
    qualities = site.get('qualities')
    print('Quality aliases for {name}:'.format(**site))
    if qualities is None:
      print('  None')
    else:
      print('  Alias: yt-dlp identifier')
      for alias, qid in qualities.items():
        print(f'  {alias:>5s}: {qid}')
    return

  if not args.playlist:
    download_video(
      args.url, args.quality, args.title, args.outdir, args.convert_to, args.posted,
      args.interactive, args.get_filename, args.cookies, args.exe
    )
  else:
    if args.check_existing:
      downloaded = set(get_ids_from_directory(args.check_existing))
    else:
      downloaded = set()
    for vid in get_ids_from_playlist(args.url, args.exe):
      if vid in downloaded:
        logging.info(f'Info: Skipping video {vid}: already downloaded.')
        continue
      site = get_site(args.url)
      url = get_url_from_id(vid, site)
      download_video(
        url, args.quality, args.title, args.outdir, args.convert_to, args.posted, False,
        args.get_filename, args.cookies, args.exe
      )


def download_video(
    url, quality, title, outdir, convert_to, posted, interactive, get_filename, cookies, exe
  ):
  site = get_site(url)
  if site is None:
    fail('URL must be from a supported site.')

  qual_key = get_quality_key(quality, site)

  formatter = Formatter(
    site, url, exe, title=title, convert=convert_to, interactive=interactive, posted=posted,
  )
  fmt_str = formatter.get_format_string()

  end_args = get_end_args(url, fmt_str, outdir, qual_key, cookies, convert_to)

  if get_filename:
    cmd = [exe, '--get-filename'] + end_args
  else:
    cmd = [exe] + YOUTUBE_DL_ARGS + end_args
    # Kludge to work around bug in dailymotion downloader.
    if site['name'] == 'dailymotion':
      cmd.remove('--add-metadata')
    print(format_command(cmd))
  subprocess.run(cmd)


def get_site(url):
  domain = urllib.parse.urlparse(url).netloc
  for name, site in SUPPORTED_SITES.items():
    supported_domain = site['domain']
    if domain.endswith(supported_domain):
      site['name'] = name
      return site
  supported_sites_str = ', '.join([site['domain'] for site in SUPPORTED_SITES.values()])
  logging.error(f'Error: URL {url!r} is not from a supported site({supported_sites_str}).')
  return None


def get_qualities_str(supported_sites):
  qualities_strs = []
  for site, info in supported_sites.items():
    if 'qualities' in info:
      mappings = {}
      for shorthand, target in info['qualities'].items():
        short_list = mappings.setdefault(target, [])
        short_list.append(shorthand)
      mapping_strs = []
      for target, short_list in mappings.items():
        mapping_str = '/'.join(short_list)+' →  '+target
        mapping_strs.append(mapping_str)
      quality_str = site+' ('+', '.join(mapping_strs)+')'
      qualities_strs.append(quality_str)
  if len(qualities_strs) == 1:
    return qualities_strs[0]
  elif len(qualities_strs) == 2:
    return qualities_strs[0]+' and '+qualities_strs[1]
  else:
    return ', '.join(qualities_strs[:-1])+', and '+qualities_strs[-1]


def get_quality_key(quality_arg, site):
  if quality_arg:
    qualities = site.get('qualities', {})
    qual_key = qualities.get(quality_arg)
    if qual_key is None:
      logging.warning(
        f'Warning: --quality {quality_arg} unrecognized. Passing verbatim to youtube-dl.'
      )
      qual_key = quality_arg
    return qual_key
  return None


def get_end_args(url, fmt_str, outdir, qual_key, cookies, convert_to):
  end_args = ['-o', str(outdir/fmt_str), url]
  if qual_key:
    end_args = ['-f', qual_key] + end_args
  if cookies:
    end_args = ['--cookies', str(cookies)] + end_args
  if convert_to:
    end_args = ['--extract-audio', '--audio-format', convert_to] + end_args
  return end_args


def format_command(cmd):
  escaped_args = [None]*len(cmd)
  for i, arg in enumerate(cmd):
    escaped_args[i] = arg
    for char in ' ?&;\'":$':
      if char in arg:
        escaped_args[i] = repr(arg)
        break
  return '$ '+' '.join(escaped_args)


class Formatter:

  def __init__(self, site, url, exe, title=None, convert=False, interactive=True, posted=None):
    self.site = site
    self.url = url
    self.exe = exe
    self.convert = convert
    self.interactive = interactive
    self.posted = posted
    if title is None:
      self.title = '%(title)s'
    else:
      self.title = title

  def get_format_string(self):
    if self.convert:
      return self.title+'.%(ext)s'
    else:
      metaformatter = getattr(self, 'format_{name}'.format(**self.site))
      return self.title+' '+metaformatter()

  def format_youtube(self):
    uploader_id = get_format_value(self.url, 'uploader_id', self.exe)
    # Only use both uploader and uploader_id if the id is a channel id like "UCZ5C1HBPMEcCA1YGQmqj6Iw"
    if re.search(r'^UC[a-zA-Z0-9_-]{22}$', uploader_id):
      return '[src %(uploader)s, %(uploader_id)s] [posted %(upload_date)s] [id %(id)s].%(ext)s'
    else:
      logging.warning(
        f'uploader_id {uploader_id} looks like a username, not a channel id. Omitting channel id..'
      )
      return '[src %(uploader_id)s] [posted %(upload_date)s] [id %(id)s].%(ext)s'

  def format_vimeo(self):
    return '[src vimeo.com%%2F%(uploader_id)s] [posted %(upload_date)s] [id %(id)s].%(ext)s'

  def format_twitch(self):
    match = re.search(r'^https?://clips.twitch.tv/([^/?]+)((\?|/).*)?$', self.url)
    assert match, self.url
    video_id = match.group(1)
    return f'[src twitch.tv%%2F%(creator)s] [posted %(upload_date)s] [id {video_id}].%(ext)s'

  def format_facebook(self):
    FACEBOOK_REGEX = r'facebook\.com/[^/?]+/videos/[0-9]+'
    url = self.url
    good_url = False
    match = re.search(FACEBOOK_REGEX, url)
    if match:
      good_url = True
    else:
      cmd = ('curl', '-s', '--write-out', '%{redirect_url}', '-o', os.devnull, url)
      logging.info(format_command(cmd))
      result = subprocess.run(cmd, stdout=subprocess.PIPE)
      new_url = str(result.stdout, 'utf8')
      match = re.search(FACEBOOK_REGEX, new_url)
      if match:
        url = new_url
        good_url = True
    escaped_url = self.simplify_url(url)
    return f'[posted %(upload_date)s] [src {escaped_url}].%(ext)s'

  #TODO: Figure out how to get the username.
  #      Tiktok urls look like `https://www.tiktok.com/@wallacenoises/video/6915592857738923269`.
  #      Getting the id at the end now works with `%(id)s`, but as of 2021.1.8 there still doesn't
  #      seem to be a way to get the @ username. `uploader_id` gives a long integer, `uploader`
  #      gives the user's display name, and `channel`, `channel_id`, and `creator` all give "NA".
  def format_tiktok(self):
    escaped_url = self.simplify_url(self.url)
    return f'[posted %(upload_date)s] [src {escaped_url}].%(ext)s'

  def format_instagram(self):
    return self._format_instatwit()

  def format_twitter(self):
    return self._format_instatwit()

  def _format_instatwit(self):
    upload_date = get_format_value(self.url, 'upload_date', self.exe)
    if upload_date == 'NA':
      if self.posted:
        posted_fmt = f'[posted {self.posted}] '
      else:
        posted_fmt = get_posted_str(self.interactive)
    else:
      posted_fmt = '[posted %(upload_date)s] '
    domain = self.site['domain']
    return posted_fmt+f'[src {domain}%%2F%(uploader_id)s] [id %(id)s].%(ext)s'

  def format_dailymotion(self):
    return self._format_posted_url()

  def format_patreon(self):
    return self._format_posted_url()

  def _format_posted_url(self):
    simple_url = self.simplify_url(self.url)
    return f'[posted %(upload_date)s] [src {simple_url}].%(ext)s'

  def simplify_url(self, url):
    parts = urllib.parse.urlparse(url)
    assert parts.netloc.endswith(self.site['domain']), url
    simple_url = self.site['domain']+parts.path
    return double_escape_url(simple_url)


def get_posted_str(interactive):
  posted_fmt = ''
  logging.warning('Warning: No upload date could be obtained!')
  if interactive:
    logging.warning(
      'Please enter a string to use in the [posted YYYYMMDD] field. Or just hit enter to skip.'
    )
    posted_str = input('Posted: ')
    if 1 < len(posted_str) < 30:
      posted_fmt = f'[posted {posted_str}] '
    else:
      logging.warning(
        f'Warning: Did not receive a valid string (saw {posted_str!r}). Skipping..'
      )
  return posted_fmt


def get_format_value(url, key, exe):
  cmd = (exe, '--get-filename', '--playlist-items', '1', '-o', f'%({key})s', url)
  logging.info(format_command(cmd))
  result = subprocess.run(cmd, stdout=subprocess.PIPE, encoding='utf8')
  return result.stdout.rstrip('\r\n')


def double_escape_url(url):
  """Percent-encode a URL, then escape the %'s so they're safe for youtube-dl format strings."""
  return urllib.parse.quote(url, safe='').replace('%', '%%')


def get_ids_from_directory(dirpath):
  for dirpath, dirnames, filenames in os.walk(dirpath):
    for filename in filenames:
      try:
        vid = parse_id_from_filename(filename)
      except ValueError as error:
        logging.info(error)
      else:
        yield vid


def parse_id_from_filename(filename):
  fields1 = filename.split('[id ')
  if len(fields1) <= 1:
    raise ValueError(f'Filename has no [id XXXXX] field: {filename!r}')
  elif len(fields1) > 2:
    raise ValueError(f'Filename has multiple [id XXXXX] fields: {filename!r}')
  fields2 = fields1[1].split(']')
  if len(fields2) <= 1:
    raise ValueError(f'Filename has malformed [id XXXXX] field (no ending bracket): {filename!r}')
  return fields2[0]


def get_ids_from_playlist(url, exe):
  cmd = (exe, '--get-id', url)
  logging.info(format_command(cmd))
  result = subprocess.run(cmd, encoding='utf8', stdout=subprocess.PIPE)
  return result.stdout.splitlines()


def get_url_from_id(vid, site):
  try:
    base_url = site['base_url']
  except KeyError:
    raise RuntimeError(f'Playlist downloading not supported for site {site["domain"]}')
  return base_url.format(id=vid)


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
