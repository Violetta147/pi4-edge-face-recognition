# Nhận diện khuôn mặt kích hoạt bằng siêu âm trên Raspberry Pi 4

Hệ thống chờ HC-SR04 phát hiện vật thể ở gần, sau đó mở USB webcam và xử lý **một khuôn mặt**. PAD (chống giả mạo) luôn bật. Camera được giải phóng khi rời vùng hoặc khi đã cấp quyền; model được nạp một lần lúc khởi động.

| Kết quả | Phản hồi |
|---|---|
| Mặt thật và khớp người đã đăng ký | Servo đến 90°, giữ **5 giây**, quay về 0°, ngắt PWM; cả hai LED tắt |
| Mặt thật nhưng không khớp cơ sở dữ liệu | Bật LED **xanh**, không chạy servo |
| Giả mạo (spoof) | Bật LED **đỏ**, không chạy servo |
| Chờ cảm biến, chưa có mặt, đang xác minh hoặc lỗi AI | Hai LED tắt, không cấp quyền mới |

**Xanh có nghĩa là người thật chưa đăng ký**, theo yêu cầu của dự án. Không sử dụng cách hiểu màu của ma trận LED ở phiên bản trước.

## Luồng xử lý

1. Khoảng cách hợp lệ <= `ACTIVATION_DISTANCE_CM` (mặc định 60 cm) bắt đầu phiên xử lý. Không mở camera hoặc chạy suy luận trước khi có kích hoạt.
2. Detector có thể tìm nhiều mặt, nhưng chỉ mặt có diện tích lớn nhất được đưa vào PAD và ArcFace. Đây không phải cơ chế định danh người bằng cảm biến siêu âm.
3. Cần 3 lần PAD thật liên tiếp trước khi so khớp, rồi 3 lần khớp **cùng tên** liên tiếp mới cấp quyền. Mỗi lần so khớp dùng đặc trưng mới của frame hiện tại. Một kết quả spoof sẽ hủy chuỗi kết quả thật/khớp đang tích lũy.
4. Mất mặt, đổi vùng mặt rõ rệt, lỗi camera/AI hoặc tín hiệu khoảng cách không hợp lệ đều xóa bằng chứng đang tích lũy. Lỗi AI không được coi là người chưa đăng ký.
5. Trước khi chạy servo, đo lại khoảng cách và yêu cầu vẫn <=60 cm. Servo chỉ được kích một lần mỗi lượt tiếp cận; không kích lặp khi người đứng yên.
6. Sau chu kỳ servo, cần đo được khoảng cách >= `RELEASE_DISTANCE_CM` (80 cm) liên tục 1 giây để cho phép lượt mới. Trong vùng 60–80 cm, giữ trạng thái kích hoạt trước đó để tránh chập chờn.

**Mất echo không được coi là người đã rời đi** vì có thể là cảm biến bị ngắt. Khi dùng HC-SR04, bố trí vật nền trong tầm đo phía sau vùng hoạt động để có số đo xa hợp lệ cho bước tái kích hoạt. Log `SENSOR_ERROR` nghĩa là không có số đo hợp lệ; không cấp quyền. Khoảng cách dựa trên đo thời gian bằng phần mềm trên Linux, cần kiểm tra thực tế bằng thước.

## Phần cứng và chân mặc định

Dùng **HC-SR04 và servo vị trí 0–180°**. Servo quay liên tục không thể điều khiển góc 90° theo cách này. Các chân bên dưới là đề xuất có thể sửa trong `.env`, chưa phải xác nhận dây thực tế của bạn.

| Thiết bị | BCM | Chân vật lý Pi 4 |
|---|---|---|
| HC-SR04 TRIG | 23 | 16 |
| HC-SR04 ECHO qua chia áp | 24 | 18 |
| Servo tín hiệu | 18 | 12 |
| LED xanh qua điện trở | 17 | 11 |
| LED đỏ qua điện trở | 27 | 13 |
| GND chung | — | Ví dụ chân 6 |

- **Tắt nguồn khi thay dây.** Ngắt mạch ma trận 10 LED cũ khỏi GPIO23/24/18 vì các chân này nay dùng cho cảm biến và servo. Module `peripherals/led_matrix.py` được giữ làm tham khảo cũ, không còn được `run.py` sử dụng.
- HC-SR04 thông thường cấp 5 V; ECHO là 5 V, **không nối thẳng vào GPIO Pi**. Dùng bộ chuyển mức hoặc chia áp. Ví dụ từ tài liệu gpiozero: ECHO → 330 Ω → nút nối GPIO24; nút này → 470 Ω → GND (khoảng 2.94 V). HC-SR04P có thể khác, xem thông số đúng module.
- Mỗi LED dùng điện trở 220–330 Ω, cathode về GND.
- Servo dùng nguồn ngoài đúng điện áp/dòng của loại servo; nối GND nguồn servo chung với Pi. Không cấp nguồn motor từ chân GPIO hoặc 3.3 V.
- Chân servo không phát PWM khi vừa mở app. Chỉ sau xác thực thành công mới đặt về góc gốc 0°, chờ 0.5 giây, chuyển đến 90°, giữ 5 giây, quay về 0°, chờ 0.5 giây rồi detach. Thời gian về vị trí, pulse min/max cần hiệu chỉnh theo servo và tải thực tế. Ngắt PWM không bảo đảm giữ lực ở góc đó.
- Chu kỳ servo dùng timer độc lập với vòng đọc camera/AI. Thoát app sẽ hủy timer và ngắt PWM ngay, **không tự di chuyển servo về 0° khi Ctrl+C giữa chu kỳ**.

Tham khảo: [gpiozero HC-SR04](https://gpiozero.readthedocs.io/en/stable/api_input.html#distancesensor-hc-sr04), [gpiozero AngularServo](https://gpiozero.readthedocs.io/en/stable/api_output.html#angularservo).

## Cài lần đầu

Pi 4, Raspberry Pi OS Trixie aarch64, USB webcam. Từ Remote shell Raspberry Pi Connect:

```bash
git clone https://github.com/Violetta147/pi4-edge-face-recognition.git
cd pi4-edge-face-recognition
bash setup.sh
source venv/bin/activate
```

`requirements.txt` đã bổ sung `insightface==2.1`. Không cần CUDA/PyTorch. Setup không ghi đè `.env` đã có.

## Cập nhật bản đã chạy trên Pi

Không xóa `faces.db`, `faces/` hoặc venv. Dừng app bằng Ctrl+C trước khi cập nhật:

```bash
cd ~/IoT/pi4-edge-face-recognition
git pull --ff-only origin main
source venv/bin/activate
python -m pip install 'insightface==2.1'
cp .env .env.before-ultrasonic
nano .env
```

Giữ cấu hình camera/model/ngưỡng đang dùng. Thêm hoặc sửa các mục sau theo dây thật:

```dotenv
ULTRASONIC_TRIGGER_PIN=23
ULTRASONIC_ECHO_PIN=24
SERVO_PIN=18
LED_GREEN_PIN=17
LED_RED_PIN=27
ACTIVATION_DISTANCE_CM=60
RELEASE_DISTANCE_CM=80
REARM_CLEAR_SECONDS=1
SERVO_HOME_ANGLE=0
SERVO_OPEN_ANGLE=90
SERVO_HOLD_SECONDS=5
SERVO_RETURN_HOME=true
SERVO_MOVE_SECONDS=0.5
```

Các giá trị bổ sung mặc định được mô tả trong `.env.example`. `LED_RED_PINS`, `LED_GREEN_PINS`, `ENABLE_PAD` cũ không còn được dùng; `--no-pad` và phím `p` bị loại bỏ để không có đường bỏ qua PAD cho servo.

## Kiểm tra cảm biến trước khi chạy AI

Lệnh này chỉ đo khoảng cách, không điều khiển LED hoặc servo:

```bash
GPIOZERO_PIN_FACTORY=lgpio python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
from access_control import Settings
from gpiozero import DigitalInputDevice, DigitalOutputDevice
from peripherals.access_hardware import AccessHardware
import time

# Dùng cùng hàm đo khoảng cách của app mà không khởi tạo servo.
s = Settings.from_env()
with DigitalOutputDevice(s.trigger_pin, initial_value=False) as trigger, DigitalInputDevice(s.echo_pin, pull_up=False) as echo:
    probe = type('Probe', (), {})()
    probe.settings, probe.trigger, probe.echo = s, trigger, echo
    probe.clock, probe.sleep = time.monotonic, time.sleep
    probe.last_trigger = float('-inf')
    try:
        while True:
            print('Distance cm:', AccessHardware.distance_cm(probe), flush=True)
            time.sleep(s.poll_seconds)
    except KeyboardInterrupt:
        pass
PY
```

Đưa vật vào khoảng 30/60/100 cm để đối chiếu bằng thước. `None` là phép đo không hợp lệ/timeout, cần kiểm tra dây/nguồn/module. Dừng bằng Ctrl+C.

## Đăng ký và chạy

Người đã có `faces.db` trên Pi **không cần đăng ký lại**. Số mẫu DB có thể là 1 vì chương trình lưu vector trung bình của 5 ảnh.

```bash
python enroll.py --list
# Chỉ dùng nếu cần đăng ký mới, Enter từng lần trong Remote shell:
env -u DISPLAY -u WAYLAND_DISPLAY python enroll.py --name "Violetta" --camera 0 --samples 5
export GPIOZERO_PIN_FACTORY=lgpio
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -u run.py --headless --camera 0
```

Để có cửa sổ ảnh, mở Terminal ngay trong desktop Screen sharing và bỏ `--headless`. Cửa sổ chỉ hiển thị một mặt đang xử lý; khi chờ cảm biến sẽ hiển thị nền trống/trạng thái. Bấm `q` trong cửa sổ để thoát hoặc Ctrl+C trong terminal. Remote shell dùng Ctrl+C.

Nếu dùng `GPIOZERO_PIN_FACTORY=mock`, ECHO mặc định không tự tạo xung: app sẽ không kích hoạt. Mock không phải cách bỏ qua cảm biến; dùng bài test bên dưới để mô phỏng luồng, không kiểm tra phần cứng bằng trạng thái mock.

## Checklist nghiệm thu trên Pi

- [ ] Khi khoảng cách >80 cm: `WAITING`, không mở webcam, không chạy suy luận từng frame.
- [ ] Khi vật đến <=60 cm: bắt đầu đọc camera, chỉ một mặt được xử lý dù ảnh có nhiều người.
- [ ] Người thật chưa đăng ký: `UNKNOWN`, chỉ LED xanh sáng, servo không chạy.
- [ ] Ảnh/màn hình bị PAD phân loại spoof: `SPOOF`, chỉ LED đỏ sáng, servo không chạy. Ghi lại sai phân loại thực tế nếu có.
- [ ] Người đã đăng ký: đủ xác nhận mới có `REAL_KNOWN`; servo 0→90°, giữ 5 giây, về 0° và ngắt PWM.
- [ ] Tiếp tục đứng trước cảm biến: `WAIT_CLEAR`, không tự mở lại.
- [ ] Sau khi đo >=80 cm liên tục 1 giây, tiến lại gần: cho phép lượt xác minh mới.
- [ ] Mất mặt/ngắt echo/lỗi AI: không cấp quyền mới và không dùng lại tên cũ.
- [ ] Ctrl+C giải phóng webcam, tắt LED, ngắt PWM và đóng GPIO.

PAD và ngưỡng cosine vẫn là mô hình suy luận, có thể sai. Việc code yêu cầu PAD/so khớp không phải bằng chứng đạt mức bảo mật hoặc độ chính xác trên mọi người/ánh sáng. Cần kiểm tra đúng webcam, cảm biến và servo thực tế.

## Kiểm thử local

```bash
python -m unittest discover -s tests -v
```

Các bài test dùng camera/AI/GPIO giả để kiểm tra quyết định, lỗi cảm biến/camera/AI, chỉ xử lý một mặt, không cấp quyền cho spoof/unknown, timer servo và tái kích hoạt. Không cần Pi hoặc ONNX Runtime để chạy chúng; cần `python-dotenv` để import entrypoint. Không thay thế thử nghiệm vật lý trên Pi.

Kiểm chứng local ngày 19/10/2026: **23 bài test đạt**; kiểm tra bổ sung với gpiozero 2.0.1 `MockFactory`/`MockPWMPin` đạt cho ánh xạ LED và chu kỳ servo 0→90→giữ 5 giây→0→detach. Chưa chạy luồng siêu âm/servo mới với model, webcam và GPIO thật trên Raspberry Pi. Kết quả nhận diện bạn đã chạy trước đó thuộc phiên bản camera cũ.

File `KE_HOACH_CHAY_PI_TRONG_30_PHUT.md` giữ nguyên tiến độ bản triển khai cũ. Với luồng siêu âm/servo mới, dùng hướng dẫn và checklist trong README này; các bước ma trận 10 LED và `--no-pad` trong kế hoạch cũ không còn áp dụng.
