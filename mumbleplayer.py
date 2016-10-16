# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import pymumble
import audioread
import time
import audioop
import os
from progressbar import ProgressBar, Bar, Percentage, Timer
import datetime


class Playlist(object):
    def __init__(self):
        self.files = []

    def load_from_file(self, playlist):
        rel_base_path = os.path.dirname(os.path.abspath(playlist))
        with open(playlist, 'rb') as f:
            for row in f:
                # Ignore comment rows
                if row.startswith('#'):
                    continue

                row = row.rstrip('\r\n')
                if os.path.isabs(row):
                    self.files.append(row)
                else:
                    self.files.append(os.path.join(rel_base_path, row))

    def add_file(self, filename):
        self.files.append(filename)


class MumblePlayer(object):
    def __init__(self, host, port, user, password=None, key_file=None, cert_file=None):
        self.host = host
        self.port = port
        self.mumble = pymumble.Mumble(host, port=port,
                                      user=user, password=password,
                                      keyfile=key_file, certfile=cert_file)

    def connect(self):
        self.mumble.start()
        self.mumble.is_ready()
        self.mumble.users.myself.comment("Mumble player v0.1")
        self.mumble.users.myself.unmute()
        self.mumble.set_bandwidth(200000)

    def join_channel(self, channel):
        self.mumble.channels.find_by_name(channel).move_in()

    def play(self, playlist, volume=None):
        song_number = 0
        total_songs = len(playlist.files)
        for filename in playlist.files:
            with audioread.audio_open(filename) as f:
                widgets = [
                    '[{}/{}] {}'.format(song_number, total_songs, os.path.basename(filename)),
                    ' ', Bar(left='[', right=']'),
                    ' ', Percentage(),
                    ' ', Timer(),
                    ' of ', str(datetime.timedelta(seconds=f.duration)).split('.', 2)[0]
                ]
                with ProgressBar(max_value=f.duration, widgets=widgets) as progress:
                    bytes_position = 0
                    last_updated = 0
                    bps = 2 * f.channels * f.samplerate
                    for buf in f:
                        # Update progressbar when necessary
                        bytes_position += len(buf)
                        sec_position = bytes_position / bps
                        if int(sec_position) > last_updated:
                            progress.update(sec_position)
                            last_updated = int(sec_position)

                        # Wait if there is no need to fill the buffer
                        while self.mumble.sound_output.get_buffer_size() > 1.0:
                            time.sleep(0.01)

                        # Convert audio if necessary
                        if f.channels != 1:
                            buf = audioop.tomono(buf, 2, 1, 1)
                        if f.samplerate != 48000:
                            buf, _ = audioop.ratecv(buf, 2, 1, f.samplerate, 48000, None)
                        if volume:
                            buf = audioop.mul(buf, 2, volume)

                        # Insert to mumble buffer
                        self.mumble.sound_output.add_sound(buf)
            song_number += 1


def main():
    parser = argparse.ArgumentParser(description='Mumble audio player')
    parser.add_argument('-f', '--file',
                        type=str,
                        dest='filename',
                        metavar="FILE",
                        help='Audio file',
                        required=True)
    parser.add_argument('-k', '--keyfile',
                        type=str,
                        dest='keyfile',
                        help='SSL Private key file',
                        default='key.pem')
    parser.add_argument('-e', '--certfile',
                        type=str,
                        dest='certfile',
                        help='SSL Public key file',
                        default='cert.pem')
    parser.add_argument('-a', '--address',
                        type=str,
                        dest='address',
                        help='Address',
                        default='localhost')
    parser.add_argument('-P', '--port',
                        type=int,
                        dest='port',
                        help='Port',
                        default=64738)
    parser.add_argument('-u', '--username',
                        type=str,
                        dest='username',
                        help='Username',
                        default='mumbleplayer')
    parser.add_argument('-p', '--password',
                        type=str,
                        dest='password',
                        help='Password',
                        default=None)
    parser.add_argument('-c', '--channel',
                        type=str,
                        dest='channel',
                        required=True)
    parser.add_argument('-v', '--volume',
                        type=float,
                        dest='volume',
                        default=1.0)
    args = parser.parse_args()

    if args.volume < 0.01:
        args.volume = 0.01
    if args.volume > 2.0:
        args.volume = 2.0

    # Create a playlist
    playlist = Playlist()
    if os.path.splitext(args.filename)[1] == '.m3u':
        playlist.load_from_file(args.filename)
    else:
        playlist.add_file(args.filename)
    print("Playlist created with {} items.".format(len(playlist.files)))

    # Start up the player
    player = MumblePlayer(args.address, args.port,
                          user=args.username, password=args.password,
                          key_file=args.keyfile, cert_file=args.certfile)
    try:
        player.connect()
        player.join_channel(args.channel)
        player.play(playlist, volume=args.volume)
    except KeyboardInterrupt:
        print("Playback interrupted.")

if __name__ == '__main__':
    main()
