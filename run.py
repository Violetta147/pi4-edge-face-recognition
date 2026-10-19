"""Proximity-triggered, single-face PAD/recognition and servo access control."""

import argparse
from dataclasses import replace
import math
import os
from pathlib import Path
import signal
import time

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

from access_control import AccessPolicy, Settings


def parse_args():
    parser = argparse.ArgumentParser(description='Ultrasonic + one face + PAD + servo')
    parser.add_argument('--camera', type=int, default=int(os.getenv('CAMERA_INDEX', '0')))
    parser.add_argument('--headless', action='store_true', help='Log through Remote shell')
    parser.add_argument('--threshold', type=float, help='Override cosine match threshold')
    parser.add_argument('--pad', action='store_true', help='Compatibility flag; PAD is always enabled')
    return parser.parse_args()


class EdgeApp:
    def __init__(self, args, settings=None, hardware=None, detector=None,
                 embedder=None, antispoof=None, db=None, camera_factory=None):
        # Injection permits testing full control flow without Pi hardware or model weights.
        self.args = args
        self.settings = settings or Settings.from_env()
        if args.threshold is not None:
            self.settings = replace(self.settings, match_threshold=args.threshold)
        self.policy = AccessPolicy(self.settings)
        self.hardware = hardware
        self.cap = None
        self.running = True
        self.status = 'WAITING'
        self.detail = ''
        self.name = None
        self.score = None
        self.pad_score = None
        self.last_log = float('-inf')
        self.last_error = float('-inf')
        self.previous_status = None
        self.args.headless = args.headless or not (os.getenv('DISPLAY') or os.getenv('WAYLAND_DISPLAY'))
        try:
            if self.hardware is None:
                from peripherals.access_hardware import AccessHardware
                self.hardware = AccessHardware(self.settings)
            if detector is None:
                from detection import create_detector
                detector = create_detector(det_size=(640, 640), conf_thresh=0.5)
            if embedder is None:
                from recognition import FaceEmbedder
                embedder = FaceEmbedder()
            if antispoof is None:
                from antispoof import AntiSpoofPredictor
                antispoof = AntiSpoofPredictor(threshold_logit=self.settings.pad_threshold)
            if db is None:
                from database.local_db import LocalDB
                db = LocalDB()
            self.detector, self.embedder, self.antispoof, self.db = detector, embedder, antispoof, db
            if camera_factory is None:
                import cv2
                camera_factory = cv2.VideoCapture
            self.camera_factory = camera_factory
        except Exception:
            self.cleanup()
            raise

    def reset_evidence(self):
        self.policy.reset_face()
        self.name = self.score = self.pad_score = None

    def release_camera(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def read_frame(self):
        import cv2
        if self.cap is None:
            self.cap = self.camera_factory(self.args.camera)
            if not self.cap.isOpened():
                raise RuntimeError(f'Cannot open /dev/video{self.args.camera}')
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise RuntimeError('Camera did not return a frame')
        return frame

    def process_frame(self, frame):
        from alignment import align_face

        detections = self.detector.detect(frame)
        if not detections:
            self.reset_evidence()
            return 'NO_FACE', None
        # Only this face is sent to PAD and ArcFace, regardless of detector count.
        face = max(detections, key=lambda d: max(0, d['bbox'][2] - d['bbox'][0]) *
                   max(0, d['bbox'][3] - d['bbox'][1]))
        self.policy.begin_face(face['bbox'])
        self.name = self.score = None
        is_real, _, self.pad_score = self.antispoof.predict(frame, face['bbox'])
        status = self.policy.observe_pad(is_real, self.pad_score)
        if status != 'REAL':
            return status, face
        landmarks = face.get('landmarks')
        aligned = align_face(frame, landmarks) if landmarks is not None and len(landmarks) == 5 else None
        if aligned is None:
            self.reset_evidence()
            return 'VERIFYING', face
        feature = self.embedder.extract(aligned)
        if feature is None:
            self.reset_evidence()
            return 'VERIFYING', face
        self.name, self.score = self.db.match_face(feature, threshold=self.settings.match_threshold)
        if not math.isfinite(self.score):
            raise ValueError('Invalid cosine score')
        status = self.policy.observe_match(self.name, self.score)
        if status == 'REAL_KNOWN':
            # Recheck proximity after inference, before touching the actuator.
            distance = self.hardware.distance_cm()
            if distance is None or not math.isfinite(distance) or not 0 < distance <= self.settings.activation_cm:
                self.policy.granted = False
                self.policy.active = False
                self.reset_evidence()
                return 'WAITING', None
            self.hardware.grant()
            print(f'[ACCESS] REAL_KNOWN: {self.name} | cosine={self.score:.3f} | servo 90 deg', flush=True)
        return status, face

    def step(self):
        self.hardware.tick()
        distance = self.hardware.distance_cm()
        enabled = self.policy.update_distance(distance, time.monotonic(), self.hardware.servo_busy)
        frame, face = None, None
        self.detail = ''
        if not enabled:
            self.release_camera()
            self.reset_evidence()
            if self.hardware.servo_busy:
                self.status = 'SERVO_ACTIVE'
            elif distance is None or not math.isfinite(distance) or distance <= 0:
                self.status = 'SENSOR_ERROR'
            else:
                self.status = 'WAIT_CLEAR' if self.policy.granted else 'WAITING'
        else:
            try:
                frame = self.read_frame()
                self.status, face = self.process_frame(frame)
            except Exception as exc:
                self.reset_evidence()
                self.release_camera()
                self.status = 'ERROR'
                self.detail = str(exc)
                if time.monotonic() - self.last_error >= 2:
                    print(f'[ERROR] {exc}', flush=True)
                    self.last_error = time.monotonic()
        self.hardware.show(self.status)
        now = time.monotonic()
        if self.status != self.previous_status or now - self.last_log >= 1:
            d = 'invalid/no echo' if distance is None else f'{distance:.1f} cm'
            name = f' | {self.name} cosine={self.score:.3f}' if self.name and self.score is not None else ''
            pad = f' | PAD={self.pad_score:.3f}' if self.pad_score is not None else ''
            print(f'[{self.status}] distance={d}{name}{pad}', flush=True)
            self.last_log, self.previous_status = now, self.status
        if not self.args.headless:
            self.draw(frame, face)
        return self.status

    def draw(self, frame, face):
        import cv2
        import numpy as np
        if frame is None:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        else:
            frame = frame.copy()
        color = {'SPOOF': (0, 0, 255), 'UNKNOWN': (0, 255, 0),
                 'REAL_KNOWN': (255, 200, 0)}.get(self.status, (0, 215, 255))
        if face:
            x1, y1, x2, y2 = face['bbox']
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = self.status + (f': {self.name}' if self.name else '')
        cv2.putText(frame, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, color, 2)
        cv2.putText(frame, '[Q] Exit | PAD always ON', (10, 52), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
        cv2.imshow('Pi access control', frame)
        if cv2.waitKey(1) & 0xFF in (ord('q'), 27):
            self.running = False

    def run(self):
        print(f'[START] One face | PAD always ON | activation <= {self.settings.activation_cm:g} cm', flush=True)
        print('[START] UNKNOWN -> green; SPOOF -> red; REAL_KNOWN -> servo. Ctrl+C to exit.', flush=True)
        try:
            while self.running:
                start = time.monotonic()
                self.step()
                time.sleep(max(0, self.settings.poll_seconds - (time.monotonic() - start)))
        finally:
            self.cleanup()

    def cleanup(self):
        self.release_camera()
        if self.hardware is not None:
            self.hardware.close()
        if not self.args.headless:
            import cv2
            cv2.destroyAllWindows()


def main():
    app = EdgeApp(parse_args())

    def stop(_signum, _frame):
        app.running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    app.run()


if __name__ == '__main__':
    main()
