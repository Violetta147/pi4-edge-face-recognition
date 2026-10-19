"""Configuration and verification policy, independent of GPIO and AI packages."""

from dataclasses import dataclass
import math
import os


@dataclass(frozen=True)
class Settings:
    trigger_pin: int = 23
    echo_pin: int = 24
    servo_pin: int = 18
    green_pin: int = 17
    red_pin: int = 27
    activation_cm: float = 400.0
    obstacle_grace_seconds: float = 2.0
    sensor_timeout: float = 0.03
    poll_seconds: float = 0.1
    servo_hold_seconds: float = 5.0
    servo_move_seconds: float = 0.5
    servo_home_angle: float = 0.0
    servo_open_angle: float = 90.0
    servo_min_pulse: float = 0.001
    servo_max_pulse: float = 0.002
    servo_return_home: bool = True
    real_confirmations: int = 3
    match_confirmations: int = 3
    face_iou: float = 0.3
    match_threshold: float = 0.4
    pad_threshold: float = -0.373

    def __post_init__(self):
        pins = [self.trigger_pin, self.echo_pin, self.servo_pin, self.green_pin, self.red_pin]
        if len(set(pins)) != len(pins) or any(not 0 <= p <= 27 for p in pins):
            raise ValueError('GPIO must be distinct BCM pins in 0..27')
        numeric = [v for v in vars(self).values() if isinstance(v, (int, float))]
        if not all(math.isfinite(v) for v in numeric):
            raise ValueError('Configuration values must be finite')
        if not 0 < self.activation_cm < self.sensor_timeout * 17150:
            raise ValueError('Obstacle range must fit ultrasonic timeout range')
        if min(self.obstacle_grace_seconds, self.poll_seconds, self.servo_hold_seconds,
               self.servo_move_seconds, self.servo_min_pulse) <= 0:
            raise ValueError('Durations must be positive')
        if self.poll_seconds < 0.06 or not 0.005 <= self.sensor_timeout <= 0.05:
            raise ValueError('Use poll >= 0.06 s and echo timeout 0.005..0.05 s')
        if not self.servo_min_pulse < self.servo_max_pulse < 0.02:
            raise ValueError('Servo pulses must satisfy 0 < min < max < 0.02 s')
        if not all(0 <= angle <= 180 for angle in (self.servo_home_angle, self.servo_open_angle)):
            raise ValueError('Servo angles must be in 0..180 degrees')
        if abs(abs(self.servo_open_angle - self.servo_home_angle) - 90) > 1e-6:
            raise ValueError('Home and open angles must be 90 degrees apart')
        if min(self.real_confirmations, self.match_confirmations) < 1:
            raise ValueError('Confirmation counts must be at least 1')
        if not 0 < self.face_iou <= 1 or not -1 <= self.match_threshold <= 1:
            raise ValueError('Invalid IoU or cosine threshold')

    @classmethod
    def from_env(cls):
        fields = {
            'trigger_pin': ('ULTRASONIC_TRIGGER_PIN', int),
            'echo_pin': ('ULTRASONIC_ECHO_PIN', int),
            'servo_pin': ('SERVO_PIN', int),
            'green_pin': ('LED_GREEN_PIN', int),
            'red_pin': ('LED_RED_PIN', int),
            'activation_cm': ('OBSTACLE_MAX_DISTANCE_CM', float),
            'obstacle_grace_seconds': ('OBSTACLE_GRACE_SECONDS', float),
            'sensor_timeout': ('ULTRASONIC_TIMEOUT_SECONDS', float),
            'poll_seconds': ('SENSOR_POLL_SECONDS', float),
            'servo_hold_seconds': ('SERVO_HOLD_SECONDS', float),
            'servo_move_seconds': ('SERVO_MOVE_SECONDS', float),
            'servo_home_angle': ('SERVO_HOME_ANGLE', float),
            'servo_open_angle': ('SERVO_OPEN_ANGLE', float),
            'servo_min_pulse': ('SERVO_MIN_PULSE_SECONDS', float),
            'servo_max_pulse': ('SERVO_MAX_PULSE_SECONDS', float),
            'real_confirmations': ('PAD_REAL_CONFIRMATIONS', int),
            'match_confirmations': ('MATCH_CONFIRMATIONS', int),
            'match_threshold': ('MATCH_THRESHOLD', float),
            'pad_threshold': ('FAS_LOGIT_THRESHOLD', float),
        }
        values = {field: cast(os.environ[key]) for field, (key, cast) in fields.items()
                  if key in os.environ}
        flag = os.getenv('SERVO_RETURN_HOME', 'true').lower().strip()
        if flag not in ('true', 'false', '1', '0', 'yes', 'no'):
            raise ValueError('SERVO_RETURN_HOME must be true or false')
        values['servo_return_home'] = flag in ('true', '1', 'yes')
        return cls(**values)


def bbox_iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda box: max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    union = area(a) + area(b) - intersection
    return intersection / union if union > 0 else 0.0


def servo_parameters(settings):
    """Calibrate the used 90-degree travel, not an unmeasured 180-degree range.

    Defaults map 0 -> 1000 us and 90 -> 2000 us. Physical angles must be measured.
    """
    return {
        'min_angle': min(settings.servo_home_angle, settings.servo_open_angle),
        'max_angle': max(settings.servo_home_angle, settings.servo_open_angle),
        'min_pulse_width': settings.servo_min_pulse,
        'max_pulse_width': settings.servo_max_pulse,
        'initial_angle': None,
    }


class AccessPolicy:
    """Any valid obstacle enables verification, with a short echo-dropout grace."""

    def __init__(self, settings):
        self.settings = settings
        self.active = False
        self.granted = False
        self.last_obstacle = None
        self.reset_face()

    def reset_face(self):
        self.bbox = None
        self.real_count = 0
        self.match_count = 0
        self.candidate = None

    def update_distance(self, distance_cm, now, servo_busy=False):
        valid = (distance_cm is not None and math.isfinite(distance_cm)
                 and 0 < distance_cm <= self.settings.activation_cm)
        if valid:
            self.last_obstacle = now
        self.active = self.obstacle_recent(now)
        if servo_busy:
            self.reset_face()
            return False
        if self.granted:
            # Servo finished: discard the old identity and verify again, without retreat.
            self.granted = False
            self.reset_face()
        if not self.active:
            self.reset_face()
        return self.active

    def obstacle_recent(self, now):
        return (self.last_obstacle is not None
                and 0 <= now - self.last_obstacle <= self.settings.obstacle_grace_seconds)

    def begin_face(self, bbox):
        if self.bbox is None or bbox_iou(self.bbox, bbox) < self.settings.face_iou:
            self.reset_face()
        self.bbox = bbox

    def observe_pad(self, is_real, score):
        if not self.active or self.granted:
            self.reset_face()
            return 'WAITING'
        if not math.isfinite(score):
            self.reset_face()
            return 'ERROR'
        if not is_real:
            self.real_count = self.match_count = 0
            self.candidate = None
            return 'SPOOF'
        self.real_count += 1
        return 'REAL' if self.real_count >= self.settings.real_confirmations else 'VERIFYING'

    def observe_match(self, name, score):
        if (not self.active or self.granted or self.real_count < self.settings.real_confirmations
                or not math.isfinite(score)):
            self.match_count = 0
            self.candidate = None
            return 'VERIFYING'
        if name is None or score < self.settings.match_threshold:
            self.match_count = 0
            self.candidate = None
            return 'UNKNOWN'
        self.match_count = self.match_count + 1 if name == self.candidate else 1
        self.candidate = name
        if self.match_count < self.settings.match_confirmations:
            return 'VERIFYING'
        self.granted = True
        return 'REAL_KNOWN'
