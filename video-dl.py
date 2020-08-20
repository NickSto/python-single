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

#TODO: WARC??
#      Looks like there's no WARC feature as of June 2020, though IA has requested the feature:
#      https://github.com/ytdl-org/youtube-dl/issues/21983
#      It seems what the Archive does currently is it uses youtube-dl --get-url to extract the
#      direct url to the Youtube video, then manually downloads with curl or wget.
#      Note: Currently, you get two video urls with this method. It seems one has the video, and
#      the other has the audio. Not sure if you can select different qualities.

DESCRIPTION = """Download and label a video using youtube-dl."""
YOUTUBE_DL_ARGS = ['--no-mtime', '--add-metadata', '--xattrs']
VALID_CONVERSIONS = ['mp3', 'm4a', 'flac', 'aac', 'wav']
SUPPORTED_SITES = {
  'youtube': {
    'domain':'youtube.com',
    'qualities': {
      '360':'18',
      '640':'18',
      '480':'135+250',  # 80k audio, 480p video
      '720':'22',
      '1280':'22',
    }
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
  }
}
QUALITY_SITES = [name for name, site in SUPPORTED_SITES.items() if 'qualities' in site]


def make_argparser():
  parser = argparse.ArgumentParser(description=DESCRIPTION)
  parser.add_argument('url',
    help='Video url.')
  parser.add_argument('title', nargs='?',
    help='Video title for filename.')
  parser.add_argument('-F', '--formats', action='store_true',
    help='Just print the available video quality options.')
  parser.add_argument('-f', '--quality',
    help='Video quality to request. Shorthands are available for {}. Anything else will be passed '
      'on literally to youtube-dl.'.format(', '.join(QUALITY_SITES)))
  parser.add_argument('-o', '--out-dir', type=pathlib.Path,
    help='Save the video to this directory.')
  parser.add_argument('-n', '--get-filename', action='store_true')
  parser.add_argument('-c', '--convert-to', choices=VALID_CONVERSIONS,
    help='Give a file extension to convert the video to this audio format. The file will be named '
      '"{title}.{ext}".')
  parser.add_argument('-p', '--posted',
    help='The string to insert into the [posted YYYYMMDD] field, if none can be automatically '
      'determined.')
  parser.add_argument('-I', '--non-interactive', dest='interactive', default=True,
    action='store_const', const=False,
    help='Do not prompt the user for input. Proceed fully automatically.')
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

  if not shutil.which('youtube-dl'):
    fail("Error: 'youtube-dl' command not found.")

  if args.formats:
    subprocess.run(('youtube-dl', '-F', args.url))
    return

  site = get_site(args.url)
  if site is None:
    fail('URL must be from a supported site.')

  qual_key = get_quality_key(args.quality, site)

  formatter = Formatter(
    site, args.url, title=args.title, convert=args.convert_to, interactive=args.interactive,
    posted=args.posted,
  )
  fmt_str = formatter.get_format_string()

  end_args = get_end_args(args.url, fmt_str, args.out_dir, qual_key, args.convert_to)

  if args.get_filename:
    cmd = ['youtube-dl', '--get-filename'] + end_args
  else:
    cmd = ['youtube-dl'] + YOUTUBE_DL_ARGS + end_args
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


def get_end_args(url, fmt_str, out_dir, qual_key, convert_to):
  end_args = ['-o', str(out_dir/fmt_str), url]
  if qual_key:
    end_args = ['-f', qual_key] + end_args
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

  def __init__(self, site, url, title=None, convert=False, interactive=True, posted=None):
    self.site = site
    self.url = url
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
    uploader_id = get_format_value(self.url, 'uploader_id')
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
      result = subprocess.run(cmd, stdout=subprocess.PIPE)
      new_url = str(result.stdout, 'utf8')
      match = re.search(FACEBOOK_REGEX, new_url)
      if match:
        url = new_url
        good_url = True
    escaped_url = self.simplify_url(url)
    return f'[posted %(upload_date)s] [src {escaped_url}].%(ext)s'

  #TODO: TikTok
  #      Research so far: neither uploader_id, uploader, nor creator seem to work.
  #      Not even ext, though it'll probably just be .mp4.
  #      They seem to be working on a fix, but it's made slow progress from Oct 2019 to Jun 2020.
  #      - I think this refers to pull request #22838

  def format_instagram(self):
    return self._format_instatwit()

  def format_twitter(self):
    return self._format_instatwit()

  def _format_instatwit(self):
    upload_date = get_format_value(self.url, 'upload_date')
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


def get_format_value(url, key):
  cmd = ('youtube-dl', '--get-filename', '-o', f'%({key})s', url)
  result = subprocess.run(cmd, stdout=subprocess.PIPE)
  output = str(result.stdout, 'utf8')
  return output.rstrip('\r\n')


def double_escape_url(url):
  """Percent-encode a URL, then escape the %'s so they're safe for youtube-dl format strings."""
  return urllib.parse.quote(url, safe='').replace('%', '%%')


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
