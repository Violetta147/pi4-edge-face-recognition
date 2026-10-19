import argparse
from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from access_control import AccessPolicy, Settings
from peripherals.access_hardware import AccessHardware
from run import EdgeApp


FACE = {'bbox': (0, 0, 100, 100), 'landmarks': [[10, 10]] * 5}


class FakeHardware:
    def __init__(self):
        self.distance = 30
        self.servo_busy = False
        self.grants = 0
        self.status = None
        self.closed = False

    def distance_cm(self):
        return self.distance

    def tick(self):
        pass

    def show(self, status):
        self.status = status

    def grant(self):
        self.grants += 1
        self.servo_busy = True

    def close(self):
        self.closed = True


class FakeCamera:
    def __init__(self):
        self.released = False
        self.ok = True

    def isOpened(self):
        return True

    def set(self, *args):
        pass

    def read(self):
        return self.ok, object() if self.ok else None

    def release(self):
        self.released = True


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.hardware = FakeHardware()
        self.camera = FakeCamera()
        self.faces = [FACE]
        self.real = True
        self.name = 'Violetta'
        self.calls = {'camera': 0, 'detector': 0, 'pad': 0, 'embedding': 0}
        self.pad_boxes = []

        def camera_factory(index):
            self.calls['camera'] += 1
            return self.camera

        def detect(frame):
            self.calls['detector'] += 1
            return self.faces

        def predict(frame, bbox):
            self.calls['pad'] += 1
            self.pad_boxes.append(bbox)
            return self.real, 0.9, 1.0 if self.real else -5.0

        def extract(frame):
            self.calls['embedding'] += 1
            return object()

        self.app = EdgeApp(
            argparse.Namespace(camera=0, threshold=None, headless=True),
            settings=self.settings, hardware=self.hardware,
            detector=SimpleNamespace(detect=detect),
            embedder=SimpleNamespace(extract=extract),
            antispoof=SimpleNamespace(predict=predict),
            db=SimpleNamespace(match_face=lambda *a, **k: (self.name, .8)),
            camera_factory=camera_factory)
        self.alignment = patch.dict('sys.modules', {
            'alignment': SimpleNamespace(align_face=lambda *a: object()),
            'cv2': SimpleNamespace(CAP_PROP_FRAME_WIDTH=3, CAP_PROP_FRAME_HEIGHT=4,
                                   CAP_PROP_BUFFERSIZE=38)})
        self.alignment.start()

    def tearDown(self):
        self.app.cleanup()
        self.alignment.stop()

    def steps(self, count):
        return [self.app.step() for _ in range(count)]

    def test_far_or_invalid_distance_never_opens_camera_or_runs_ai(self):
        for distance in (100, None, float('nan'), 0, -1):
            self.hardware.distance = distance
            self.app.step()
        self.assertEqual(sum(self.calls.values()), 0)
        self.assertEqual(self.hardware.grants, 0)

    def test_largest_face_only_processed(self):
        small = dict(FACE, bbox=(1, 1, 21, 21))
        self.faces = [small, FACE]
        self.app.step()
        self.assertEqual(self.pad_boxes, [FACE['bbox']])
        self.assertEqual(self.calls['pad'], 1)

    def test_spoof_never_runs_arcface_or_servo(self):
        self.real = False
        self.assertEqual(self.steps(8), ['SPOOF'] * 8)
        self.assertEqual(self.calls['embedding'], 0)
        self.assertEqual(self.hardware.grants, 0)

    def test_real_unknown_is_green_status_without_servo(self):
        self.name = None
        self.steps(5)
        self.assertEqual(self.hardware.status, 'UNKNOWN')
        self.assertEqual(self.hardware.grants, 0)

    def test_known_requires_confirmations_and_only_one_cycle_per_encounter(self):
        self.assertNotIn('REAL_KNOWN', self.steps(4))
        self.assertEqual(self.app.step(), 'REAL_KNOWN')
        self.assertEqual(self.hardware.grants, 1)
        before = dict(self.calls)
        self.steps(3)
        self.assertEqual(self.calls, before)
        self.hardware.servo_busy = False
        self.assertEqual(self.steps(5), ['WAIT_CLEAR'] * 5)
        self.assertEqual(self.hardware.grants, 1)
        self.assertTrue(self.camera.released)

    def test_sensor_loss_discards_previous_votes(self):
        self.steps(4)
        self.hardware.distance = None
        self.assertEqual(self.app.step(), 'SENSOR_ERROR')
        self.hardware.distance = 30
        self.assertNotIn('REAL_KNOWN', self.steps(4))
        self.assertEqual(self.hardware.grants, 0)

    def test_missing_or_different_face_discards_votes(self):
        self.steps(4)
        self.faces = []
        self.assertEqual(self.app.step(), 'NO_FACE')
        self.faces = [dict(FACE, bbox=(200, 200, 300, 300))]
        self.assertNotIn('REAL_KNOWN', self.steps(4))

    def test_spoof_after_real_clears_match_evidence(self):
        self.steps(4)
        self.real = False
        self.assertEqual(self.app.step(), 'SPOOF')
        self.real = True
        self.assertNotIn('REAL_KNOWN', self.steps(4))

    def test_no_cached_identity_for_new_person(self):
        self.steps(4)
        self.name = None
        self.assertEqual(self.app.step(), 'UNKNOWN')
        self.assertEqual(self.hardware.grants, 0)

    def test_changed_known_identity_needs_its_own_confirmation_streak(self):
        self.steps(4)
        self.name = 'Other user'
        self.assertEqual(self.app.step(), 'VERIFYING')
        self.assertEqual(self.hardware.grants, 0)
        self.assertEqual(self.app.step(), 'VERIFYING')
        self.assertEqual(self.app.step(), 'REAL_KNOWN')

    def test_new_encounter_requires_new_verification_after_servo_and_clear(self):
        self.steps(5)
        self.hardware.servo_busy = False
        self.hardware.distance = 100
        with patch('run.time.monotonic', return_value=10):
            self.app.step()
        with patch('run.time.monotonic', return_value=12):
            self.app.step()
        self.hardware.distance = 30
        self.assertNotIn('REAL_KNOWN', self.steps(4))
        self.assertEqual(self.hardware.grants, 1)
        self.assertEqual(self.app.step(), 'REAL_KNOWN')
        self.assertEqual(self.hardware.grants, 2)

    def test_camera_failure_discards_evidence_and_does_not_grant(self):
        self.steps(4)
        self.camera.ok = False
        self.assertEqual(self.app.step(), 'ERROR')
        self.assertEqual(self.app.policy.real_count, 0)
        self.assertEqual(self.hardware.grants, 0)

    def test_distance_checked_again_immediately_before_actuation(self):
        self.steps(4)
        with patch.object(self.hardware, 'distance_cm', side_effect=[30, 120]):
            self.assertEqual(self.app.step(), 'WAITING')
        self.assertEqual(self.hardware.grants, 0)
        self.assertFalse(self.app.policy.granted)

    def test_ai_failure_not_unknown_and_does_not_grant(self):
        with patch.object(self.app.antispoof, 'predict', side_effect=RuntimeError('model failed')):
            self.assertEqual(self.app.step(), 'ERROR')
        self.assertEqual(self.hardware.grants, 0)
        self.assertEqual(self.app.policy.real_count, 0)


class PolicyTests(unittest.TestCase):
    def test_hysteresis_and_valid_clear_required_to_rearm(self):
        p = AccessPolicy(Settings())
        self.assertFalse(p.update_distance(70, 0))
        self.assertTrue(p.update_distance(60, 1))
        self.assertTrue(p.update_distance(70, 2))
        p.granted = True
        self.assertFalse(p.update_distance(80, 3, servo_busy=True))
        p.update_distance(100, 4)
        p.update_distance(None, 5)
        self.assertTrue(p.granted)
        p.update_distance(100, 6)
        p.update_distance(100, 7.01)
        self.assertFalse(p.granted)
        self.assertTrue(p.update_distance(30, 8))

    def test_bad_configuration_rejected_before_hardware(self):
        for kwargs in ({'echo_pin': 23}, {'activation_cm': 100},
                       {'servo_hold_seconds': 0}, {'servo_open_angle': 80},
                       {'pad_threshold': float('nan')}, {'poll_seconds': 0.01}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(Settings(), **kwargs)


class FakeDevice:
    def __init__(self, pin, **kwargs):
        self.value = kwargs.get('initial_value', 0)
        self.angles = []
        self.detached = False
        self.closed = False

    @property
    def angle(self):
        return self.angles[-1] if self.angles else None

    @angle.setter
    def angle(self, value):
        self.angles.append(value)

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0

    def detach(self):
        self.detached = True

    def close(self):
        self.closed = True


class FakeTimer:
    pending = []

    def __init__(self, seconds, callback):
        self.seconds = seconds
        self.callback = callback
        self.cancelled = False

    def start(self):
        self.pending.append(self)

    def cancel(self):
        self.cancelled = True

    @classmethod
    def fire(cls):
        timer = cls.pending.pop(0)
        if not timer.cancelled:
            timer.callback()
        return timer.seconds


class HardwareTests(unittest.TestCase):
    def setUp(self):
        FakeTimer.pending = []
        self.mock_gpio = patch.dict('sys.modules', {'gpiozero': SimpleNamespace(
            AngularServo=FakeDevice, LED=FakeDevice,
            DigitalInputDevice=FakeDevice, DigitalOutputDevice=FakeDevice)})
        self.mock_gpio.start()
        self.hw = AccessHardware(Settings(), timer_factory=FakeTimer)

    def tearDown(self):
        self.hw.close()
        self.mock_gpio.stop()

    def test_servo_90_degrees_hold_five_seconds_return_and_detach(self):
        self.assertEqual(self.hw.servo.angles, [])
        self.hw.grant()
        self.assertEqual(self.hw.servo.angles, [0])
        self.assertEqual(FakeTimer.fire(), .5)
        self.assertEqual(self.hw.servo.angles, [0, 90])
        self.assertEqual(FakeTimer.fire(), 5)
        self.assertEqual(self.hw.servo.angles, [0, 90, 0])
        self.assertEqual(FakeTimer.fire(), .5)
        self.assertTrue(self.hw.servo.detached)
        self.assertFalse(self.hw.servo_busy)

    def test_led_mapping_and_off_in_other_states(self):
        for status, values in [('UNKNOWN', (1, 0)), ('SPOOF', (0, 1)),
                               ('REAL_KNOWN', (0, 0)), ('ERROR', (0, 0)), ('WAITING', (0, 0))]:
            self.hw.show(status)
            self.assertEqual((self.hw.green.value, self.hw.red.value), values)

    def test_cleanup_cancels_servo_timer_and_closes_gpio(self):
        self.hw.grant()
        servo = self.hw.servo
        timer = FakeTimer.pending[0]
        self.hw.close()
        self.assertTrue(timer.cancelled)
        self.assertTrue(servo.detached)
        self.assertTrue(servo.closed)
        FakeTimer.fire()
        self.assertEqual(servo.angles, [0])

    def test_missing_echo_has_bounded_timeout(self):
        current = [0.0]

        def clock():
            current[0] += .001
            return current[0]

        self.hw.clock = clock
        self.hw.sleep = lambda seconds: None
        self.assertIsNone(self.hw.distance_cm())
        self.assertLess(current[0], .04)
        self.assertEqual(self.hw.trigger.value, 0)

    def test_stuck_high_echo_does_not_trigger_or_return_old_distance(self):
        self.hw.echo.value = 1
        self.assertIsNone(self.hw.distance_cm())
        self.assertEqual(self.hw.trigger.value, 0)

    def test_echo_pulse_is_converted_to_centimeters(self):
        current = [0.0]

        def clock():
            current[0] += .00001
            return current[0]

        class Pulse:
            @property
            def value(self):
                return .00005 <= current[0] <= .00105

        self.hw.clock = clock
        self.hw.sleep = lambda seconds: None
        self.hw.echo = Pulse()
        self.assertAlmostEqual(self.hw.distance_cm(), 17.15, delta=1)

    def test_servo_fault_detaches_and_surfaces_to_control_loop(self):
        self.hw.grant()
        with patch.object(self.hw.servo.__class__, 'angle', new_callable=unittest.mock.PropertyMock) as angle:
            angle.side_effect = RuntimeError('PWM failed')
            FakeTimer.fire()
        self.assertTrue(self.hw.servo.detached)
        self.assertFalse(self.hw.servo_busy)
        with self.assertRaises(RuntimeError):
            self.hw.tick()


if __name__ == '__main__':
    unittest.main()
