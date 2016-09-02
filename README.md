#WTV Processing

This script coordinates several tools to process recorded TV and save the files without commercials in a Plex compatible file structure.

The basic steps:

1. For each video file matching the pattern:
2. Find or create commercial file (using Comskip)
3. Find or create the subtitle file (using ccextractor)
4. Determine Series, Season, & Episode Number
4. Cut commercials out of video file & convert to h.264 w/ AAC audio
5. Cut commercials out of subtitles file
6. Save new video and new subtitles file to `[Series]/Season #/[Series] - s##e## - [Episode].[ext]`

## Installation

### Download & compile:

- http://www.ccextractor.org/doku.php
- https://github.com/erikkaashoek/Comskip

### Install packages:

Use your favorite package manager (or download & compile):

- ffmpeg
- python3

Example:

`brew install ffmpeg python3`

### Install python dependencies

`pip3 install -r requirements.txt`

Feel free to use a virtualenv

## Running

`python3 processing.py`

Optionally pass the path to the `config.ini`: `python3 processing.py path/to/config.ini`

## Configuration

See `sample_config.ini` for examples

Obtain a TVDB API account here: [http://thetvdb.com/?tab=apiregister]()

### Output Format

- ${orig_basename} - The original basename of the file (eg `path/to/video.wtv` => `video`)
- ${ext} - The appropiate file extension
- ${season} - The season number (`1` or `10`)
- ${season_padded} - The season number padded to two digits (`01` or `10`)
- ${episode} - The episode number (`1` or `10`)
- ${episode_padded} - The episode number padded to two digits (`01` or `10`)
- ${episode_name} - The episode name
- ${series} - The series name
- $$ - The character `$`

Default is `${series}/Season ${season}/${series} - s${season_padded}e${episode_padded} - ${episode_name}.${ext}` which results in something like: `The Closer/Season 1/The Closer - s01e02 - About Face.mp4`
