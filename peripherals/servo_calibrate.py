"""One servo-only calibration cycle; no camera, ultrasonic sensor, or PAD."""

import argparse
from dataclasses import replace
from pathlib import Path
import time

from access_control import Settings, servo_parameters


def main():
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    parser = argparse.ArgumentParser(description='Servo-only 0 -> 90 -> hold 5s -> 0 calibration')
    parser.add_argument('--min-us', type=float, help='Pulse at minimum used angle, in microseconds')
    parser.add_argument('--max-us', type=float, help='Pulse at maximum used angle, in microseconds')
    args = parser.parse_args()
    settings = Settings.from_env()
    overrides = {}
    if args.min_us is not None:
        overrides['servo_min_pulse'] = args.min_us / 1_000_000
    if args.max_us is not None:
        overrides['servo_max_pulse'] = args.max_us / 1_000_000
    settings = replace(settings, **overrides)
    if not 0.0005 <= settings.servo_min_pulse < settings.servo_max_pulse <= 0.0025:
        parser.error('Calibration tool accepts pulses only within 500..2500 us; check servo limits')
    params = servo_parameters(settings)
    print(f'BCM{settings.servo_pin} | {params["min_angle"]:g} deg -> {settings.servo_min_pulse*1e6:g} us'
          f' | {params["max_angle"]:g} deg -> {settings.servo_max_pulse*1e6:g} us', flush=True)
    print('Stop the main app first. Keep linkage clear; Ctrl+C immediately if it stalls/buzzes.', flush=True)
    from gpiozero import AngularServo
    with AngularServo(settings.servo_pin, **params) as servo:
        try:
            servo.angle = settings.servo_home_angle
            print('[SERVO] Home', flush=True)
            time.sleep(max(1, settings.servo_move_seconds))
            servo.angle = settings.servo_open_angle
            print('[SERVO] 90-degree command; hold 5 seconds. Measure actual travel.', flush=True)
            time.sleep(5)
            servo.angle = settings.servo_home_angle
            print('[SERVO] Return home', flush=True)
            time.sleep(max(1, settings.servo_move_seconds))
        finally:
            servo.detach()
    print('No .env changes made. If measured correct, use these settings:')
    print(f'SERVO_MIN_PULSE_SECONDS={settings.servo_min_pulse:g}')
    print(f'SERVO_MAX_PULSE_SECONDS={settings.servo_max_pulse:g}')


if __name__ == '__main__':
    main()
