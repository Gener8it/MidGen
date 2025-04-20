#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

# === Configure Qt plugin path only during development ===
if not hasattr(sys, '_MEIPASS'):
    try:
        import PyQt5
        plugin_path = os.path.join(os.path.dirname(PyQt5.__file__), 'Qt5', 'plugins', 'platforms')
        if os.path.exists(plugin_path):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
    except Exception as e:
        print("[Warning] Could not configure QT_QPA_PLATFORM_PLUGIN_PATH:", e)

import random
import tempfile
from threading import Thread

import torch  # for GPU check
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QComboBox,
    QProgressBar, QFileDialog, QMessageBox, QHBoxLayout, QGridLayout, QSlider
)
from PyQt5.QtCore import pyqtSignal, QObject, Qt
from music21 import stream, note, chord, key, meter, tempo, midi

# === Worker class for melody generation ===
class GeneratorWorker(QObject):
    progress_changed = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, tempo_bpm, pattern_type, length_sec, save_path, craziness):
        super().__init__()
        self.tempo = tempo_bpm
        self.pattern = pattern_type
        self.length = min(length_sec, 60)
        self.save_path = save_path
        self.crazy = max(-10, min(10, craziness))

    def run(self):
        try:
            use_gpu = torch.cuda.is_available() if hasattr(torch, 'cuda') else False
            print(f"Using {'GPU' if use_gpu else 'CPU'} for generation")

            # Create a new score and part
            score = stream.Score()
            part = stream.Part()
            part.append(tempo.MetronomeMark(number=self.tempo))
            part.append(meter.TimeSignature('4/4'))

            # Choose random major key
            possible_keys = ['C','D','E','F','G','A','B']
            ks = key.Key(random.choice(possible_keys), 'major')
            part.append(ks)

            # Calculate number of measures
            beats_needed = self.length * self.tempo / 60.0
            measures = int(beats_needed // 4) + 1

            for i in range(measures):
                percent = int(i / measures * 100)
                self.progress_changed.emit(percent)

                # Build chord variation
                degree = random.choice([1,4,5])
                root = ks.getPitches()[degree-1]
                chord_notes = [root, root.transpose('M3'), root.transpose('P5')]
                chord_obj = chord.Chord(chord_notes)
                base_len = {'PAD':4,'CHORD':2,'BRASS':2}.get(self.pattern,1)
                length_factor = 1 + (-self.crazy/20)
                chord_obj.quarterLength = max(0.25, base_len * length_factor)
                part.append(chord_obj)

                # Extra accent when craziness high
                if self.crazy > 5 and random.random() < (self.crazy-5)/10:
                    extra = chord.Chord(chord_notes)
                    extra.quarterLength = 0.5
                    part.append(extra)

                # Melody notes
                count = {'ARP':3,'PLUCK':4,'RAND': random.randint(2,6)}.get(self.pattern,2)
                for idx in range(count):
                    if self.pattern == 'ARP':
                        pitch = chord_notes[idx % len(chord_notes)]
                    elif self.pattern == 'PLUCK':
                        pitch = random.choice(chord_notes)
                    else:
                        pitch = random.choice(ks.getPitches())
                    note_obj = note.Note(pitch)
                    if self.crazy >= 0:
                        duration = 1.0 / (1 + self.crazy/10)
                    else:
                        duration = 1.0 * (1 + abs(self.crazy)/10)
                    note_obj.quarterLength = max(0.125, duration)
                    part.append(note_obj)

            # Final progress
            self.progress_changed.emit(100)

            # Save MIDI to temporary file then move to final path
            score.append(part)
            midi_file = midi.translate.streamToMidiFile(score)
            tmp_path = os.path.join(tempfile.gettempdir(), 'midgen_temp.mid')
            midi_file.open(tmp_path, 'wb'); midi_file.write(); midi_file.close()
            os.replace(tmp_path, self.save_path)

            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))

# === Main window UI ===
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MidGen")
        self.setFixedSize(450, 300)
        self.init_ui()
        # Styling
        self.setStyleSheet("""
        QWidget { background-color: #888888; }
        QLabel { color: white; font-size: 14px; }
        QLineEdit, QComboBox { background-color: white; border: 2px dashed #ffffff; border-radius: 10px; padding: 4px; }
        QSlider::groove:horizontal { background: #cccccc; height: 8px; border-radius: 4px; }
        QSlider::handle:horizontal { background: #ffffff; border: 1px solid #777777; width: 16px; margin: -4px 0; border-radius: 8px; }
        QPushButton { background-color: #000000; color: #ffffff; border-radius: 12px; padding: 6px 12px; }
        QPushButton:hover { background-color: #333333; }
        QProgressBar { border: 2px solid #444444; border-radius: 5px; background-color: #ffffff; }
        QProgressBar::chunk { background-color: #00cc00; }
        """)

    def init_ui(self):
        layout = QGridLayout()
        layout.setContentsMargins(15,15,15,15)
        layout.setHorizontalSpacing(20); layout.setVerticalSpacing(10)

        layout.addWidget(QLabel("Tempo (BPM):"), 0, 0)
        self.tempo_input = QLineEdit(); self.tempo_input.setPlaceholderText("e.g. 120")
        layout.addWidget(self.tempo_input, 0, 1)

        layout.addWidget(QLabel("Type:"), 1, 0)
        self.type_combo = QComboBox(); self.type_combo.addItems(["ARP","CHORD","PLUCK","PAD","BRASS","RAND"])
        layout.addWidget(self.type_combo, 1, 1)

        layout.addWidget(QLabel("Length (sec ≤60):"), 2, 0)
        self.length_input = QLineEdit(); self.length_input.setPlaceholderText("Max 60")
        layout.addWidget(self.length_input, 2, 1)

        layout.addWidget(QLabel("Craziness (-10…+10):"), 3, 0)
        self.crazy_slider = QSlider(Qt.Horizontal)
        self.crazy_slider.setRange(-10,10); self.crazy_slider.setValue(0); self.crazy_slider.setTickInterval(1)
        layout.addWidget(self.crazy_slider, 3, 1)

        layout.addWidget(QLabel("Save to:"), 4, 0)
        h_save = QHBoxLayout()
        self.save_path = QLineEdit(); self.save_path.setReadOnly(True)
        h_save.addWidget(self.save_path)
        btn_browse = QPushButton("…"); btn_browse.clicked.connect(self.browse_file)
        h_save.addWidget(btn_browse)
        layout.addLayout(h_save, 4, 1)

        self.progress_bar = QProgressBar(); layout.addWidget(self.progress_bar,5,0,1,2)
        self.percent_label = QLabel("0%"); self.percent_label.setAlignment(Qt.AlignRight)
        layout.addWidget(self.percent_label,6,0,1,2)

        self.btn_generate = QPushButton("Generate!"); self.btn_generate.clicked.connect(self.start_generation)
        layout.addWidget(self.btn_generate,7,0,1,2)

        self.setLayout(layout)

    def browse_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save MIDI", "", "MIDI Files (*.mid)")
        if path:
            if not path.lower().endswith('.mid'): path += '.mid'
            self.save_path.setText(path)

    def start_generation(self):
        try:
            tempo = int(self.tempo_input.text()); length = int(self.length_input.text())
            if length < 1 or length > 60: raise ValueError("Length out of range")
            save_to = self.save_path.text();
            if not save_to: raise ValueError("No save path specified")
        except ValueError as e:
            QMessageBox.warning(self, "Input Error", str(e)); return

        self.btn_generate.setEnabled(False)
        self.worker = GeneratorWorker(
            tempo_bpm=tempo,
            pattern_type=self.type_combo.currentText(),
            length_sec=length,
            save_path=save_to,
            craziness=self.crazy_slider.value()
        )
        self.worker.progress_changed.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.thread = Thread(target=self.worker.run, daemon=True)
        self.thread.start()

    def on_progress(self, val):
        self.progress_bar.setValue(val); self.percent_label.setText(f"{val}%")

    def on_finished(self, path):
        QMessageBox.information(self, "Done", f"MIDI saved to:\n{path}");
        self.btn_generate.setEnabled(True)

    def on_error(self, msg):
        QMessageBox.critical(self, "Error", msg);
        self.btn_generate.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(); window.show()
    sys.exit(app.exec_())
