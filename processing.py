import xml.etree.ElementTree as ET
from wtv import extract_metadata, extract_original_air_date
import tvdb_api
import os
import sys
import subprocess
import logging
import pysrt
from copy import copy
import configparser
import datetime
from wtv_db import WtvDb
import glob
from string import Template

logging.basicConfig(filename='status.log', level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
exe_logger = logging.getLogger('executable-logger')

# Configuration
configparser = configparser.ConfigParser()
if len(sys.argv) > 1:
    configparser.read(sys.argv[1])
else:
    configparser.read('config.ini')

TEMPLATE = configparser.get('directories', 'out.pattern',
                            fallback='${series}/Season ${season}/${orig_basename} - ${series} - s${season_padded}e${episode_padded} - ${episode_name}.${ext}')
TEMPLATE = Template(TEMPLATE)
WTV_IN_DIR = configparser.get('directories', 'tv.in')
TV_PATTERN = configparser.get('directories', 'tv.pattern')
COM_IN_DIR = configparser.get('directories', 'commercial.in')
SRT_IN_DIR = configparser.get('directories', 'srt.in')
TEMP_DIR = configparser.get('directories', 'temp.dir')
OUT_DIR = configparser.get('directories', 'out.dir')
DELETE_SOURCE = configparser.getboolean('directories', 'delete.source.files', fallback=True)
FFMPEG_EXE = configparser.get('ffmpeg', 'executable')
FFPROBE_EXE = configparser.get('ffprobe', 'executable')

# H.264 Preset (https://trac.ffmpeg.org/wiki/Encode/H.264)
FFMPEG_PRESET = configparser.get('ffmpeg', 'h264.preset')
# H.264 Constant Rate Factor (https://trac.ffmpeg.org/wiki/Encode/H.264#crf)
FFMPEG_CRF = configparser.get('ffmpeg', 'h264.crf')

# TVDB API credentials
TVDB_USERNAME = configparser.get('tvdb', 'username')
TVDB_USER_KEY = configparser.get('tvdb', 'userkey')
TVDB_API_KEY = configparser.get('tvdb', 'apikey')

NICE_EXE = configparser.get('nice', 'executable')
USE_NICE = configparser.getboolean('nice', 'enabled', fallback=False)

DEBUG = configparser.getboolean('main', 'debug', fallback=False)

CCEXTRACTOR_EXE = configparser.get('ccextractor', 'executable', fallback=None)
CCEXTRACTOR_RUN = configparser.getboolean('ccextractor', 'run.if.missing', fallback=False)

COMSKIP_EXE = configparser.get('comskip', 'executable', fallback=None)
COMSKIP_RUN = configparser.getboolean('comskip', 'run.if.missing', fallback=False)
COMSKIP_INI = configparser.get('comskip', 'comskip.ini', fallback=None)

DB_FILE = configparser.get('main', 'database.file', fallback='db.sqlite')

wtvdb = WtvDb(DB_FILE)
tvdb = tvdb_api.TVDB(api_key=TVDB_API_KEY, username=TVDB_USERNAME, user_key=TVDB_USER_KEY, wtvdb=wtvdb)


def execute(args):
    if USE_NICE:
        a = [NICE_EXE]
        a.extend(args)
        args = a
    logger.debug('Executing: {}'.format(args))
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    if stdout:
        exe_logger.info(stdout)
    if stderr:
        exe_logger.error(stderr)
    return p.wait()


def get_metadata(wtv_file):
    metadata = extract_metadata(wtv_file)
    series = metadata.get('Title', None)
    episode_name = metadata.get('WM/SubTitle', None)

    filename = os.path.basename(wtv_file)
    wtv_obj = wtvdb.get_wtv(filename)
    if wtv_obj and wtv_obj.selected_episode:
        ep = wtv_obj.selected_episode.episode
        season = ep.season
        episode_num = ep.episode_num
        if episode_name is None:
            episode_name = ep.name
    elif series is not None:
        # Get season & episode number
        air_date = extract_original_air_date(wtv_file, parse_from_filename=True, metadata=metadata)
        episodes = tvdb.find_episode(series, episode=episode_name, air_date=air_date)
        if len(episodes) == 1:
            season, episode_num = tvdb_api.TVDB.season_number(episodes[0])
            if episode_name is None and episodes[0]['episodeName'] is not None:
                episode_name = episodes[0]['episodeName']
        else:
            # Handle multiple options
            wtvdb.store_candidates(tvdb, filename, metadata, episodes)
            season = None
            episode_num = None
    else:
        season = None
        episode_num = None
    if episode_name is None and episode_num is not None:
        episode_name = 'Episode #{}'.format(episode_num)
    return series, episode_name, season, episode_num


def process(wtv_file, com_file, srt_file):
    # Ensure TVDB client is authenticated
    tvdb.refresh()

    series, episode_name, season, episode_num = get_metadata(wtv_file)
    if series is not None and season is not None and episode_num is not None:
        filename = os.path.basename(wtv_file)
        filename_wo_ext = os.path.splitext(filename)[0]
        out_video = os.path.join(OUT_DIR,
                                 create_filename(series, season, episode_num, episode_name, filename_wo_ext, 'mp4'))
        out_srt = os.path.join(OUT_DIR,
                               create_filename(series, season, episode_num, episode_name, filename_wo_ext, 'eng.srt'))

        if not os.path.exists(os.path.dirname(out_video)):
            os.makedirs(os.path.dirname(out_video))
        if not os.path.exists(os.path.dirname(out_srt)):
            os.makedirs(os.path.dirname(out_srt))

        commercials = parse_commercial_file(com_file)
        split_subtitles(srt_file, invert_commercial(commercials), out_srt)
        successful = convert(wtv_file, out_video, commercials)
        if successful:
            # If we finished with the WTV, delete it
            if wtvdb.get_wtv(filename) is not None:
                wtvdb.delete_wtv(filename)
            if not DEBUG and DELETE_SOURCE:
                os.remove(wtv_file)
                os.remove(com_file)
                os.remove(srt_file)
            logger.info('Completed {} => {}'.format(wtv_file, out_video))
        else:
            logger.warn('Failure to convert {}'.format(wtv_file))
    else:
        logger.warn(
            'Missing data for {}: series={}, episode_name={}, season={}, episode_num={}'.format(wtv_file, series,
                                                                                                episode_name, season,
                                                                                                episode_num))


def extract_subtitles(wtv_file, out_srt):
    execute([CCEXTRACTOR_EXE, wtv_file, '-o', out_srt])


def run_comskip(wtv_file, out_dir):
    if COMSKIP_INI:
        execute([COMSKIP_EXE, '--ini=' + COMSKIP_INI, '--output=' + out_dir, wtv_file])
    else:
        execute([COMSKIP_EXE, '--output=' + out_dir, wtv_file])


def parse_commercial_file(com_file):
    tree = ET.parse(com_file)
    root = tree.getroot()
    commercials = []
    for child in root:
        commercials.append((float(child.get('start')), float(child.get('end'))))
    return commercials


def invert_commercial(commercials):
    inverse = [(0, commercials[0][0])]
    for i in range(len(commercials) - 1):
        left = commercials[i]
        right = commercials[i + 1]
        inverse.append((left[1], right[0]))
    if len(commercials) > 1:
        inverse.append((commercials[len(commercials) - 1][1], None))
    return inverse


def to_time(c):
    c = float(c)
    hours = int(c / (60 * 60))
    minutes = int(c / 60)
    if c >= 0:
        seconds = int(c % 60)
    else:
        seconds = -int(-c % 60)
    milliseconds = int((c - int(c)) * 1000)
    return {'hours': hours, 'minutes': minutes, 'seconds': seconds, 'milliseconds': milliseconds}


def split_subtitles(srt_file, invert_commercials, out_file):
    subs = pysrt.open(srt_file)
    parts = []
    prev = 0.0
    shift = 0
    for c in invert_commercials:
        shift = shift - float(c[0]) + prev
        s = []
        for i in subs.data:
            if i.start >= to_time(c[0]) and (c[1] is None or i.start < to_time(c[1])):
                temp = copy(i)
                time = to_time(shift)
                temp.shift(hours=time['hours'], minutes=time['minutes'], seconds=time['seconds'],
                           milliseconds=time['milliseconds'])
                parts.append(temp)
            else:
                pass
            prev = c[1] if c[1] is not None else -1
    subs = pysrt.SubRipFile(items=parts)
    subs.save(out_file)


def cut_args(invert_com, out_name):
    # -ss 0 -t 10 -c:v libx264 -preset ultrafast -crf 18 -c:a aac -strict -2 0.mp4
    args = ['-ss', str(invert_com[0])]
    if invert_com[1]:
        args.extend(['-to', str(invert_com[1])])
    args.extend(['-c:v', 'libx264', '-preset', FFMPEG_PRESET, '-crf', FFMPEG_CRF, '-c:a', 'aac', '-strict', '-2'])
    args.append(out_name)
    return args


def convert(in_file, out_file, commercials):
    invert = invert_commercial(commercials)
    temp_files = []
    wo_ext = os.path.basename(in_file).replace('.wtv', '')
    try:
        args = [FFMPEG_EXE, '-i', in_file]
        for i in invert:
            temp_file = os.path.join(TEMP_DIR, wo_ext + '.' + str(len(temp_files)) + '.mp4')
            temp_files.append(temp_file)
            if os.path.isfile(temp_file):
                os.remove(temp_file)

            args.extend(cut_args(i, temp_file))

        file_list = os.path.join(TEMP_DIR, os.path.basename(in_file).replace('wtv', 'txt'))
        with open(file_list, 'w') as f:
            for file in temp_files:
                f.writelines('file \'{}\'\n'.format(file))
        ret = execute(args)
        if ret != 0:
            logger.error('Nonzero return code from ffmpeg: {}'.format(ret))
        else:
            if os.path.isfile(out_file):
                os.remove(out_file)
            # ffmpeg -f concat -i mylist.txt -c copy output
            ret = execute(
                [FFMPEG_EXE, '-safe', '0',
                 '-f', 'concat', '-i', file_list,
                 '-c:v', 'copy',
                 '-c:a', 'copy',
                 out_file])
            if ret != 0:
                logger.error('Nonzero return code from ffmpeg: {}'.format(ret))
            # Cleanup temp files
            if not DEBUG:
                for f in temp_files:
                    os.remove(f)
                os.remove(file_list)
    except Exception as e:
        logger.exception('Exception')
        return False
    return True


def process_directory(wtv_dir, com_dir, srt_dir):
    count = 0
    files = glob.glob(os.path.join(WTV_IN_DIR, TV_PATTERN))
    for wtv_file in sorted(files):
        if os.path.isfile(wtv_file):
            wtvdb.begin()
            try:
                # wtv_file = os.path.join(wtv_dir, wtv)
                wtv = os.path.basename(wtv_file)
                time = datetime.datetime.now() - datetime.timedelta(minutes=5)
                modified = datetime.datetime.fromtimestamp(os.path.getmtime(wtv_file))
                if modified < time:
                    com = wtv.replace('wtv', 'xml')
                    srt = wtv.replace('wtv', 'srt')
                    com_file = os.path.join(com_dir, com)
                    srt_file = os.path.join(srt_dir, srt)
                    if not os.path.isfile(com_file) and COMSKIP_RUN:
                        logger.debug('No commercial file for {}. Running comskip'.format(wtv_file))
                        run_comskip(wtv_file, com_dir)
                    if not os.path.isfile(srt_file) and CCEXTRACTOR_RUN:
                        logger.debug('No srt file for {}. Running ccextractor'.format(wtv_file))
                        extract_subtitles(wtv_file, srt_file)
                    if os.path.isfile(com_file) and os.path.isfile(srt_file):
                        logger.info('Processing {}'.format(wtv_file))
                        process(wtv_file, com_file, srt_file)
                        count += 1
                    else:
                        logger.warn('No commercial or srt file for {}...skipping'.format(wtv_file))
            except Exception:
                logger.exception('Exception while handling {}'.format(wtv))
            wtvdb.end()
    logger.info('Processed {} files'.format(count))


def duration(file):
    # ffprobe -v quiet -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 converted.mp4
    p = subprocess.Popen(
        [FFPROBE_EXE, '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
         file], stdout=subprocess.PIPE)
    out, err = p.communicate()
    if len(out) == 0:
        return 0.0
    return float(out)


def durations_to_invert(durations):
    ret = []
    pos = 0
    for i in durations:
        ret.append((pos, pos + i))
        pos = pos + i
    return ret


def create_filename(series, season, episode_num, episode_name, filename, extension):
    padded_season = str(season) if int(season) >= 10 else '0' + str(season)
    padded_episode_num = str(episode_num) if int(episode_num) >= 10 else '0' + str(episode_num)
    d = dict(
        series=series,
        season=season,
        episode=episode_num,
        episode_name=episode_name,
        ext=extension,
        season_padded=padded_season,
        episode_padded=padded_episode_num,
        orig_basename=filename
    )
    return TEMPLATE.substitute(d)


if __name__ == '__main__':
    process_directory(WTV_IN_DIR, COM_IN_DIR, SRT_IN_DIR)
