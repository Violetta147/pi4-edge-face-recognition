"""HC-SR04, two LEDs and a positional servo; no silent hardware fallback."""

import math
import time
import threading
from access_control import servo_parameters


class AccessHardware:
    def __init__(self, settings, clock=time.monotonic, sleep=time.sleep, timer_factory=threading.Timer):
        from gpiozero import AngularServo, DigitalInputDevice, DigitalOutputDevice, LED

        self.settings = settings
        self.clock = clock
        self.sleep = sleep
        self.devices = []
        self.servo = None
        self.stage = None
        self.deadline = 0.0
        self.lock = threading.RLock()
        self.timer_factory = timer_factory
        self.timer = None
        self.closed = False
        self.fault = None
        self.last_trigger = float('-inf')
        try:
            self.trigger = self._keep(DigitalOutputDevice(settings.trigger_pin, initial_value=False))
            self.echo = self._keep(DigitalInputDevice(settings.echo_pin, pull_up=False))
            self.green = self._keep(LED(settings.green_pin, initial_value=False))
            self.red = self._keep(LED(settings.red_pin, initial_value=False))
            self.servo = self._keep(AngularServo(
                settings.servo_pin, **servo_parameters(settings)))
        except Exception:
            self.close()
            raise

    def _keep(self, device):
        self.devices.append(device)
        return device

    @property
    def servo_busy(self):
        return self.stage is not None

    def distance_cm(self):
        """Bounded measurement: missing/stuck echo returns None, never cached distance.

        Software timing on Linux is approximate; calibrate against a ruler on the Pi.
        """
        # HC-SR04 needs spacing between pings, including the pre-servo recheck.
        self.sleep(max(0, 0.06 - (self.clock() - self.last_trigger)))
        if self.echo.value:
            return None
        self.last_trigger = self.clock()
        self.trigger.on()
        try:
            self.sleep(0.00001)
        finally:
            self.trigger.off()
        deadline = self.clock() + self.settings.sensor_timeout
        while not self.echo.value:
            if self.clock() >= deadline:
                return None
        start = self.clock()
        deadline = start + self.settings.sensor_timeout
        while self.echo.value:
            if self.clock() >= deadline:
                return None
        distance = (self.clock() - start) * 17150.0
        return distance if math.isfinite(distance) and distance > 0 else None

    def show(self, status):
        # Per requirement: green is a REAL face absent from the database.
        self.green.value = int(status == 'UNKNOWN')
        self.red.value = int(status == 'SPOOF')

    def grant(self):
        with self.lock:
            if self.closed or self.servo_busy or self.fault:
                raise RuntimeError('Servo is closed, busy or faulted')
            # Establish a known starting angle only AFTER successful authentication.
            self.servo.angle = self.settings.servo_home_angle
            self.stage = 'HOME'
            self._schedule(self.settings.servo_move_seconds)

    def _schedule(self, seconds):
        self.deadline = self.clock() + seconds
        self.timer = self.timer_factory(seconds, self._advance_servo)
        self.timer.daemon = True
        self.timer.start()

    def tick(self):
        if self.fault:
            raise RuntimeError(f'Servo cycle failed: {self.fault}')

    def _advance_servo(self):
        # Independent timer means slow camera/AI calls do not extend PWM hold time.
        with self.lock:
            if self.closed:
                return
            try:
                if self.stage == 'HOME':
                    self.servo.angle = self.settings.servo_open_angle
                    self.stage = 'OPEN'
                    self._schedule(self.settings.servo_hold_seconds)
                elif self.stage == 'OPEN' and self.settings.servo_return_home:
                    self.servo.angle = self.settings.servo_home_angle
                    self.stage = 'RETURN'
                    self._schedule(self.settings.servo_move_seconds)
                else:
                    self.servo.detach()
                    self.stage = None
                    print('[SERVO] Da ngat xung PWM; ket thuc chu ky.', flush=True)
            except Exception as exc:
                self.fault = exc
                try:
                    self.servo.detach()
                finally:
                    self.stage = None

    def close(self):
        with self.lock:
            self.closed = True
            if self.timer is not None:
                self.timer.cancel()
            if self.servo is not None:
                try:
                    self.servo.detach()
                except Exception:
                    pass
            for device in reversed(self.devices):
                try:
                    device.close()
                except Exception:
                    pass
            self.devices.clear()
            self.stage = None
