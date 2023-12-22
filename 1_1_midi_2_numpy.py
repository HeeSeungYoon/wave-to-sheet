#!/usr/bin/env python
# -*- coding: utf8 -*-

from mido import MidiFile
from unidecode import unidecode
import glob
import numpy as np
import os
from tqdm import tqdm
import matplotlib.pyplot as plt

#######
# Pianorolls dims are  :   TIME  *  PITCH

class Read_midi(object):
    def __init__(self, song_path, quantization):
        ## Metadata
        self.__song_path = song_path
        self.__quantization = quantization

        ## Pianoroll
        self.__T_pr = None

        ## Private misc
        self.__num_ticks = None
        self.__T_file = None

    @property
    def quantization(self):
        return self.__quantization

    @property
    def T_pr(self):
        return self.__T_pr

    @property
    def T_file(self):
        return self.__T_file

    def get_total_num_tick(self):
        # Midi length should be written in a meta message at the beginning of the file,
        # but in many cases, lazy motherfuckers didn't write it...

        # Read a midi file and return a dictionnary {track_name : pianoroll}
        mid = MidiFile(self.__song_path)

        # Parse track by track
        num_ticks = 0
        for i, track in enumerate(mid.tracks):
            tick_counter = 0
            for message in track:
                # Note on
                time = float(message.time)
                tick_counter += time
            num_ticks = max(num_ticks, tick_counter)
        self.__num_ticks = num_ticks

    def get_pitch_range(self):
        mid = MidiFile(self.__song_path)
        min_pitch = 200
        max_pitch = 0
        for i, track in enumerate(mid.tracks):
            for message in track:
                if message.type in ['note_on', 'note_off']:
                    pitch = message.note
                    if pitch > max_pitch:
                        max_pitch = pitch
                    if pitch < min_pitch:
                        min_pitch = pitch
        return min_pitch, max_pitch

    def get_time_file(self):
        # Get the time dimension for a pianoroll given a certain quantization
        mid = MidiFile(self.__song_path)
        # Tick per beat
        ticks_per_beat = mid.ticks_per_beat
        # Total number of ticks
        self.get_total_num_tick()
        # Dimensions of the pianoroll for each track
        self.__T_file = int((self.__num_ticks / ticks_per_beat) * self.__quantization)
        return self.__T_file

    def read_file(self):
        # Read the midi file and return a dictionnary {track_name : pianoroll}
        mid = MidiFile(self.__song_path)
        # Tick per beat
        ticks_per_beat = mid.ticks_per_beat

        # Get total time
        self.get_time_file()
        T_pr = self.__T_file
        # Pitch dimension
        N_pr = 128
        pianoroll = {}

        def add_note_to_pr(note_off, notes_on, pr):
            pitch_off, _, time_off = note_off
            # Note off : search for the note in the list of note on,
            # get the start and end time
            # write it in th pr
            match_list = [(ind, item) for (ind, item) in enumerate(notes_on) if item[0] == pitch_off]
            if len(match_list) == 0:
                print("Try to note off a note that has never been turned on")
                # Do nothing
                return

            # Add note to the pr
            pitch, velocity, time_on = match_list[0][1]
            pr[time_on:time_off, pitch] = velocity
            # Remove the note from notes_on
            ind_match = match_list[0][0]
            del notes_on[ind_match]
            return

        # Parse track by track
        counter_unnamed_track = 0
        for i, track in enumerate(mid.tracks):
            # Instanciate the pianoroll
            pr = np.zeros([T_pr, N_pr])
            time_counter = 0
            notes_on = []
            for message in track:

                # print message
                # Time. Must be incremented, whether it is a note on/off or not
                time = float(message.time)
                time_counter += time / ticks_per_beat * self.__quantization
                # Time in pr (mapping)
                time_pr = int(round(time_counter))
                # Note on
                if message.type == 'note_on':
                    # Get pitch
                    pitch = message.note
                    # Get velocity
                    velocity = message.velocity
                    if velocity > 0:
                        notes_on.append((pitch, velocity, time_pr))
                    elif velocity == 0:
                        add_note_to_pr((pitch, velocity, time_pr), notes_on, pr)
                # Note off
                elif message.type == 'note_off':
                    pitch = message.note
                    velocity = message.velocity
                    add_note_to_pr((pitch, velocity, time_pr), notes_on, pr)

            # We deal with discrete values ranged between 0 and 127
            #     -> convert to int
            pr = pr.astype(np.int16)
            if np.sum(np.sum(pr)) > 0:
                name = unidecode(track.name)
                name = name.rstrip('\x00')
                if name == u'':
                    name = 'unnamed' + str(counter_unnamed_track)
                    counter_unnamed_track += 1
                if name in pianoroll.keys():
                    # Take max of the to pianorolls
                    pianoroll[name] = np.maximum(pr, pianoroll[name])
                else:
                    pianoroll[name] = pr
        return pianoroll

def get_pianoroll_time(pianoroll):
    T_pr_list = []
    for k, v in pianoroll.items():
        T_pr_list.append(v.shape[0])
    if not len(set(T_pr_list)) == 1:
        print("Inconsistent dimensions in the new PR")
        return None
    return T_pr_list[0]

def get_pitch_dim(pianoroll):
    N_pr_list = []
    for k, v in pianoroll.items():
        N_pr_list.append(v.shape[1])
    if not len(set(N_pr_list)) == 1:
        print("Inconsistent dimensions in the new PR")
        raise NameError("Pr dimension")
    return N_pr_list[0]

def dict_to_matrix(pianoroll):
    T_pr = get_pianoroll_time(pianoroll)
    N_pr = get_pitch_dim(pianoroll)
    rp = np.zeros((T_pr, N_pr), dtype=np.int16)
    for k, v in pianoroll.items():
        rp = np.maximum(rp, v)
    return rp

if __name__ == '__main__':
    path = './midi_and_sheet/'
    midi_files = glob.glob(path + '*.mid')
    midis = []
    for file in midi_files:
        try:
            midi = Read_midi(file, 4).read_file()
            midi = dict_to_matrix(midi)
            midi = midi.T
            midis.append(midi)
        except:
            continue

    size = 256

    for i in range(len(midis)):
        midis[i] = np.resize(midis[i],(size, size))

    # visualizing midi file
    for midi, file in tqdm(zip(midis,midi_files), total=len(midis)):
        # plt.plot(range(midi.shape[0]), np.multiply(np.where(midi > 0, 1, 0), range(1, 129)), marker='.',
        #          markersize=1, linestyle='')
        # plt.title(file)
        plt.imshow(midi, cmap='gray')
        if not os.path.isdir('./images/midi'):
            os.mkdir('./images/midi')
        img_file = './images/midi/{}.png'.format(os.path.basename(file))
        plt.savefig(img_file)
    plt.close()

    midis = np.asarray(midis)
    midis = np.expand_dims(midis, axis=3)
    print(midis.shape)

    save_path = './data/'
    if not os.path.isdir(save_path):
        os.mkdir(save_path)

    file_name = 'midi_{}.npy'.format(midis.shape[1:3])
    np.save(save_path + file_name, midis)






