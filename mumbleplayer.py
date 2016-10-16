# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import pymumble
from pymumble.constants import PYMUMBLE_CONN_STATE_FAILED
import audioread
import time
import audioop
import os
from progressbar import ProgressBar, Bar, Percentage, Timer
import datetime
import random
import threading

APP_NAME = 'MumblePlayer'
APP_VERSION = '0.1'


class PlayerException(Exception):
    pass


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
        if os.path.isabs(filename):
            self.files.append(filename)
        else:
            rel_base_path = os.path.dirname(os.path.abspath(__name__))
            self.files.append(os.path.join(rel_base_path, filename))

    def shuffle(self):
        random.shuffle(self.files)


class ThreadedStreamer(threading.Thread):
    def __init__(self, mumble, filename, volume=None):
        super(ThreadedStreamer, self).__init__()
        self._run = True
        self.filename = filename
        self.mumble = mumble
        self.volume = volume
        self.bytes_position = 0
        self.seconds_position = 0
        self.seconds_duration = 0
        self.ready = False

    def wait_ready(self):
        while not self.ready:
            time.sleep(0.1)

    def run(self):
        rate_conversion_state = None
        # Open audio file with Audioread module. This may crash if proper decoders are not installed!
        with audioread.audio_open(self.filename) as dec:
            self.seconds_duration = dec.duration
            bps = 2 * dec.channels * dec.samplerate
            self.ready = True
            for buf in dec:
                # Wait if there is no need to fill the buffer
                while self.mumble.sound_output.get_buffer_size() > 2.0 and self._run:
                    time.sleep(0.01)
                if not self._run:
                    return

                # Update position
                self.bytes_position += len(buf)
                self.seconds_position = self.bytes_position / bps

                # Convert audio if necessary. We want precisely 16bit 48000Hz mono audio for mumble.
                if dec.channels != 1:
                    buf = audioop.tomono(buf, 2, 0.5, 0.5)
                if dec.samplerate != 48000:
                    buf, rate_conversion_state = audioop.ratecv(buf, 2, 1, dec.samplerate, 48000, rate_conversion_state)
                if self.volume:
                    buf = audioop.mul(buf, 2, self.volume)

                # Insert to mumble outgoing buffer
                self.mumble.sound_output.add_sound(buf)

    def stop(self):
        self._run = False


class MumblePlayer(object):
    def __init__(self, host, port, user, password=None, key_file=None, cert_file=None):
        self.host = host
        self.port = port
        self.player_thread = None
        self.mumble = pymumble.Mumble(host, port=port, reconnect=True,
                                      user=user, password=password,
                                      keyfile=key_file, certfile=cert_file)

    def connect(self):
        self.mumble.start()
        self.mumble.is_ready()
        if self.mumble.connected == PYMUMBLE_CONN_STATE_FAILED:
            raise PlayerException("Connection failed")
        self.mumble.users.myself.unmute()
        self.mumble.sound_output.set_audio_per_packet(0.04)  # We want to send big packages since latency doesnt matter

    def set_bandwidth(self, bandwidth=200000):
        self.mumble.set_bandwidth(bandwidth)

    def set_comment(self, comment):
        self.mumble.users.myself.comment(comment)

    def join_channel(self, channel):
        self.mumble.channels.find_by_name(channel).move_in()

    def play(self, playlist, volume=None):
        song_number = 1
        total_songs = len(playlist.files)
        for filename in playlist.files:
            # Disregard nonexistent files; we don't want to crash
            if not os.path.exists(filename):
                print("File '{}' does not exist, skipping.".format(filename))
                continue

            # Start up the player thread. Make sure its member vars contain useful information.
            self.player_thread = ThreadedStreamer(self.mumble, filename, volume=volume)
            self.player_thread.start()
            self.player_thread.wait_ready()

            # Just show progress bar until the song is done
            widgets = [
                '[{}/{}] {}'.format(song_number, total_songs, os.path.basename(filename)),
                ' ', Bar(left='[', right=']'),
                ' ', Percentage(),
                ' ', Timer(format='%(elapsed)s'),
                ' of ', str(datetime.timedelta(seconds=self.player_thread.seconds_duration)).split('.', 2)[0]
            ]
            with ProgressBar(max_value=self.player_thread.seconds_duration, widgets=widgets) as progress:
                while self.player_thread.is_alive():
                    progress.update(self.player_thread.seconds_position)
                    time.sleep(0.1)

            self.player_thread.stop()
            self.player_thread.join()
            self.player_thread = None
            song_number += 1

    def stop(self):
        if self.player_thread:
            self.player_thread.stop()
            self.player_thread.join()
            self.player_thread = None


def main():
    parser = argparse.ArgumentParser(description='{} v{}'.format(APP_NAME, APP_VERSION))
    parser.add_argument('-f', '--file',
                        type=str,
                        dest='filename',
                        metavar="FILE",
                        help='Audio or m3u playlist file',
                        required=True)
    parser.add_argument('-k', '--keyfile',
                        type=str,
                        dest='keyfile',
                        metavar="FILE",
                        help='SSL Private key file',
                        default=None)
    parser.add_argument('-e', '--certfile',
                        type=str,
                        dest='certfile',
                        metavar="FILE",
                        help='SSL Public key file',
                        default=None)
    parser.add_argument('-a', '--address',
                        type=str,
                        dest='address',
                        help='Mumble server address',
                        default='localhost')
    parser.add_argument('-P', '--port',
                        type=int,
                        dest='port',
                        help='Mumble server port',
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
                        help="Mumble channel to join",
                        dest='channel',
                        required=True)
    parser.add_argument('-v', '--volume',
                        type=float,
                        dest='volume',
                        help="Playback volume, defaults to 1.0",
                        default=1.0)
    parser.add_argument('-b', '--bandwidth',
                        type=int,
                        help="Bandwidth used for transmission",
                        dest='bandwidth',
                        default=128000)
    parser.add_argument('-l', '--loop',
                        action='store_true',
                        help="Loop the playlist",
                        dest='loop')
    parser.add_argument('-s', '--shuffle',
                        action='store_true',
                        help="Shuffle the playlist (on each loop)",
                        dest='shuffle')
    args = parser.parse_args()

    # Set some volume limits -- we don't want to accidentally break anybodys ears.
    if args.volume < 0.01:
        args.volume = 0.01
    if args.volume > 2.0:
        args.volume = 2.0

    # Make sure public certificate file and key file are both either set or not set (not either or)
    if bool(args.certfile) != bool(args.keyfile):
        print("Both cert and key files must be either set or not set, not either-or!")
        exit(1)

    # Check file existence
    if args.certfile and not os.path.exists(args.certfile):
        print("Public certificate file {} does not exist!".format(args.certfile))
        exit(1)
    if args.keyfile and not os.path.exists(args.keyfile):
        print("Private key file {} does not exist!".format(args.keyfile))
        exit(1)
    if not os.path.exists(args.filename):
        print("Audio file {} does not exist!".format(args.filename))
        exit(1)

    # Print out some info
    print("Connecting to '{}:{}' as '{}'".format(args.address, args.port, args.username))
    print("Joining channel '{}'".format(args.channel))
    print("Playback volume set as '{}'".format(args.volume))
    if args.loop:
        print("Playlist will be looped")
    if args.shuffle:
        print("Playlist will be shuffled on each loop" if args.loop else "Playlist will be shuffled")
    if args.certfile and args.keyfile:
        print("Using certificates:")
        print(" * Public key = {}".format(args.certfile))
        print(" * Private key = {}".format(args.keyfile))

    # Create a playlist
    playlist = Playlist()
    if os.path.splitext(args.filename)[1] == '.m3u':
        playlist.load_from_file(args.filename)
        print("Playlist loaded with {} items.".format(len(playlist.files)))
    else:
        playlist.add_file(args.filename)

    # Start up the player
    player = MumblePlayer(args.address, args.port,
                          user=args.username, password=args.password,
                          key_file=args.keyfile, cert_file=args.certfile)

    # Attempt to connect; fail here if something goes wrong
    try:
        player.connect()
    except PlayerException as e:
        print("Error: {}".format(str(e)))
        exit(0)

    player.set_bandwidth(args.bandwidth)
    player.set_comment('{} v{}'.format(APP_NAME, APP_VERSION))
    player.join_channel(args.channel)

    # Start playback, loop if necessary. If something goes wrong, remember to kill the thread!
    try:
        while True:
            if args.shuffle:
                playlist.shuffle()
            player.play(playlist, volume=args.volume)
            if not args.loop:
                break
    except KeyboardInterrupt:
        player.stop()
        print("Playback interrupted")
    except:  # We want to be sure to kill the thread, just re-raise after that.
        player.stop()
        raise

if __name__ == '__main__':
    main()
