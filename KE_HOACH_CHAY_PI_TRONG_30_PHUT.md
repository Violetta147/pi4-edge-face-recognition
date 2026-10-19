# Kế hoạch chạy dự án trên Raspberry Pi trong 30 phút

- **Ngày lập:** 19/10/2026
- **Thiết bị:** Raspberry Pi 4B rev 1.5 (RAM 8 GB, Raspberry Pi OS 13 Trixie, `aarch64`)
- **Serial:** `1000000027d04395`
- **Repository:** https://github.com/Violetta147/pi4-edge-face-recognition

Bạn đã có sẵn **Remote shell** và có thể mở **Screen sharing** tại https://connect.raspberrypi.com.

> **Lưu ý quan trọng trước khi bắt đầu:**
> - **Mọi lệnh Bash bên dưới đều chạy trên Pi**, không chạy trong PowerShell của máy Windows.
> - **Giai đoạn cài đặt (phút 00–20):** gõ lệnh trong **Remote shell** cho nhanh.
> - **Giai đoạn mở camera (từ phút 20 trở đi):** chuyển sang mở ứng dụng **Terminal ngay bên trong màn hình Screen sharing** để cửa sổ camera hiện đúng lên màn hình desktop của Pi.
> - **Giữ nguyên tiến độ hiện tại:** các mục đã đánh dấu `[x]` bên dưới là phần bạn đã hoàn thành. Hãy làm tiếp từ mục `[ ]` đầu tiên, không cần làm lại từ đầu.

---

## Mục tiêu & Điều kiện chuẩn bị

**Lộ trình 30 phút:** Cài đặt môi trường → Đọc thử webcam → Nạp các model AI → Đăng ký 1 khuôn mặt qua cửa sổ camera → Chạy nhận diện kèm chống giả mạo (PAD) trên Screen sharing (và kiểm tra đèn LED thật nếu đã đấu mạch). Nếu giao diện đồ họa (GUI) gặp trục trặc, bạn có sẵn phương án dự phòng chạy qua Remote shell (`--headless`). *Lưu ý: Khung 30 phút là thời gian dự kiến, thực tế còn phụ thuộc vào tốc độ mạng và tốc độ tải gói trên Pi.*

**Danh sách kiểm tra trước khi bấm giờ:**
- [x] **Đã cắm USB webcam trực tiếp vào Pi.** (Webcam của chiếc laptop bạn đang ngồi nhìn trình duyệt sẽ không tự truyền sang Pi).
- [x] **Có người đứng trước webcam của Pi** để đăng ký và thử nhận diện (nếu bạn ngồi ở xa Pi thì cần một người đứng tại chỗ hỗ trợ).
- [ ] **Nếu có dùng đèn LED:** mạch đã được đấu sẵn, mỗi chân LED đều nối qua điện trở 220–330 Ω và nối chung GND. *(Nhớ tắt nguồn Pi trước khi cắm/rút dây, tuyệt đối không vừa chạy lệnh vừa sửa dây điện).*
- [x] **Pi có kết nối Internet**, dùng được quyền `sudo` và còn trống ít nhất khoảng **2 GB** bộ nhớ.

*Ghi chú về Raspberry Pi Connect:* Dịch vụ này kết nối qua Internet nên laptop và Pi không cần chung mạng Wi-Fi/LAN, không cần tìm IP hay mở port router. Tính năng **Screen sharing** truyền trực tiếp màn hình desktop của Pi lên trình duyệt, giúp bạn nhìn thấy cửa sổ camera OpenCV mà không cần viết thêm web server riêng.

---

## Phút 00–03: Kiểm tra thiết bị và webcam

- [x] Giữ nguyên tab **Remote shell** đang mở. Mở thêm một tab danh sách thiết bị trên Connect, bấm **Connect via → Screen sharing** ở thiết bị `pi` để mở màn hình desktop của Pi. Giữ song song cả 2 tab để tiện chuyển qua lại.
  *(Screen sharing yêu cầu phiên màn hình Wayland trên Pi đang chạy. Chỉ đánh dấu hoàn thành mục này khi bạn đã nhìn thấy màn hình desktop của Pi. Nếu đợi quá 1 phút vẫn không mở được màn hình, hãy cứ đi tiếp bằng Remote shell và dùng chế độ dự phòng `--headless` ở các bước sau).*

- [x] Chạy lần lượt các lệnh sau trong **Remote shell** để kiểm tra thông số máy:

```bash
hostname
cat /proc/device-tree/model; echo
grep Serial /proc/cpuinfo
uname -m
cat /etc/os-release
python3 --version
df -h "$HOME"
id
ls -l /dev/video* /dev/gpiochip* 2>/dev/null
```

**Kết quả cần thấy:**
- Đúng dòng máy Raspberry Pi 4, khớp số Serial, kiến trúc `aarch64`, hệ điều hành Debian 13 (Trixie).
- Phiên bản Python trên Trixie thường là `3.13` (lấy kết quả hiển thị thực tế trên máy bạn làm chuẩn).
- Xuất hiện các đường dẫn `/dev/video*` và `/dev/gpiochip*`. *(Lưu ý: thấy `/dev/video*` mới chỉ báo hiệu có thiết bị video, ta sẽ kiểm tra xem webcam có đọc được ảnh thật hay không ở bước sau).*

> **Dừng lại nếu sai loại camera:** Nếu bạn chưa cắm USB webcam hoặc đang cắm camera dẹt chân CSI của Pi thì hãy dừng phần test camera tại đây để đổi phần cứng. Code hiện tại của dự án đọc hình qua `cv2.VideoCapture` (dành cho USB webcam), chưa hỗ trợ luồng `Picamera2` cho camera CSI.

---

## Phút 03–12: Tải mã nguồn và cài đặt môi trường

- [x] **Cài các gói thư viện hệ thống** (chỉ cài gói cần thiết, không chạy nâng cấp toàn bộ hệ điều hành để tránh tốn thời gian):

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pip python3-gpiozero python3-lgpio libgl1 libglib2.0-0 v4l-utils
```

- [x] **Tải mã nguồn dự án (clone) về thư mục riêng trên Pi:**

```bash
mkdir -p ~/IoT
cd ~/IoT
git clone https://github.com/Violetta147/pi4-edge-face-recognition.git
cd pi4-edge-face-recognition
git rev-parse --short HEAD
```
*(Bản code đối chiếu khi viết kế hoạch này là commit `3dccf63`. Nếu thư mục dự án đã có sẵn từ trước, bạn chỉ cần gõ `cd ~/IoT/pi4-edge-face-recognition` rồi kiểm tra bằng `git status --short`, không cần xóa đi tải lại).*

- [x] **Tạo môi trường ảo (`venv`) và cài các thư viện Python:**

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --only-binary=:all: 'numpy>=1.22' 'opencv-python>=4.8' 'onnxruntime>=1.23' 'python-dotenv>=1.0' 'insightface==2.1'
python -m pip check
```

**Giải thích ngắn gọn cách cài này:**
- Cờ `--system-site-packages` giúp môi trường ảo dùng lại luôn `gpiozero` và `lgpio` vừa cài qua `apt` ở trên.
- Cờ `--only-binary=:all:` ép `pip` chỉ tải các gói đã biên dịch sẵn (wheel), giúp Pi không bị treo hàng chục phút để tự biên dịch code C++. Nếu có gói nào báo lỗi thiếu bản cài sẵn, lệnh sẽ dừng ngay và chỉ rõ tên gói đó — lúc này bạn đừng tự xóa cờ `--only-binary` để ép máy biên dịch.
- **Tại sao không chạy luôn file `setup.sh`?** Vì file `requirements.txt` trong repo hiện đang thiếu thư viện `insightface` (trong khi file `detection/scrfd_detector.py` lại cần nó). Ở đây ta cài thẳng `insightface==2.1` vì bản này có gói cài sẵn thuần Python trên PyPI, nhẹ và không bắt cài thêm PyTorch hay CUDA.

- [ ] **Nếu quá phút thứ 12 mà vẫn chưa cài xong:** hãy ghi lại tên gói hoặc dòng báo lỗi đang gặp và tập trung xử lý dứt điểm bước cài đặt. Đừng vội chạy ứng dụng nếu bước cài `pip` vẫn còn báo lỗi.

---

## Phút 12–17: Kiểm tra thư viện, model AI và webcam

- [x] **Kiểm tra xem Python đã nhận đủ các thư viện chưa:**

```bash
python -c "import cv2, numpy, onnxruntime, insightface, gpiozero, lgpio; from dotenv import load_dotenv; print('IMPORT OK'); print('OpenCV:', cv2.__version__); print('ONNX Runtime:', onnxruntime.__version__); print('InsightFace:', insightface.__version__)"
```

- [x] **Tạo file cấu hình `.env`** (lệnh dưới sẽ giữ nguyên file `.env` nếu bạn đã tạo trước đó) và giới hạn số luồng CPU:

```bash
test -f .env || cp .env.example .env
export OMP_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
```

- [x] **Thử nạp 3 model AI mặc định của dự án:**

```bash
python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
from detection import create_detector
from recognition import FaceEmbedder
from antispoof import AntiSpoofPredictor
detector = create_detector(det_size=(640, 640))
embedder = FaceEmbedder()
pad = AntiSpoofPredictor()
print('MODEL OK:', pad.model_name)
PY
```
**Kết quả cần thấy:** Hiện dòng chữ `MODEL OK`. Cả 3 file model `.onnx` đều đã có sẵn trong repo nên bạn không cần tải thêm. *(Nếu lúc chạy thấy báo lỗi ở detector rồi chương trình tự động tải gói `buffalo_s` từ mạng về, hãy copy lại toàn bộ đoạn báo lỗi đầu tiên đó — vì đó là cơ chế chữa cháy tự động của code, nghĩa là model có sẵn trong máy chưa chạy đúng).*

- [x] **Tìm đúng cổng USB webcam và đọc thử ảnh:**

```bash
v4l2-ctl --list-devices
export CAM=0
python - <<'PY'
import os
import cv2
cam = int(os.environ['CAM'])
cap = cv2.VideoCapture(cam)
try:
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok, frame = False, None
    for _ in range(10):
        ok, frame = cap.read()
        if ok and frame is not None:
            break
    assert ok and frame is not None, f'Khong doc duoc camera {cam}'
    print('CAMERA OK:', frame.shape)
finally:
    cap.release()
PY
```
**Kết quả cần thấy:** Hiện dòng `CAMERA OK: (480, 640, 3)`.
*Mẹo:* Nhìn kết quả của lệnh `v4l2-ctl --list-devices` để xem chiếc USB webcam của bạn đang gắn với số mấy. Ví dụ nếu nó nằm ở `/dev/video2`, hãy gõ `export CAM=2` rồi chạy lại đoạn code Python bên dưới. Không cần thử mò từng số của các thiết bị hệ thống khác trên Pi.

---

## Phút 17–20: Kiểm tra đèn LED (nếu đã đấu mạch)

Hệ thống đánh số chân cắm theo chuẩn **BCM** (không phải số thứ tự chân vật lý trên bo mạch):

| Cột (Slot) | LED Đỏ (Số BCM / Chân vật lý) | LED Xanh (Số BCM / Chân vật lý) |
|---|---|---|
| **1** | 27 / chân 13 | 17 / chân 11 |
| **2** | 22 / chân 15 | 18 / chân 12 |
| **3** | 23 / chân 16 | 24 / chân 18 |
| **4** | 25 / chân 22 | 12 / chân 32 |
| **5** | 16 / chân 36 | 26 / chân 37 |

**Chọn 1 trong 2 trường hợp dưới đây:**

- [ ] **Trường hợp 1 — Đã đấu sẵn mạch LED thật:** Chạy bài kiểm tra đèn bằng lệnh sau:

```bash
GPIOZERO_PIN_FACTORY=lgpio python - <<'PY'
from dotenv import load_dotenv
load_dotenv('.env')
import runpy
runpy.run_module('peripherals.led_matrix', run_name='__main__')
PY
```
Hãy nhìn trực tiếp mạch điện (hoặc nhờ người đứng cạnh Pi xem giúp) xem từng cặp đèn có sáng lần lượt **Đỏ → Xanh → Sáng cả hai** hay không. *(Lưu ý: dòng chữ `[OK]` trên màn hình chỉ báo hiệu code đã chạy xong, bạn phải nhìn thấy đèn sáng thật mới tính là đạt).*

Nếu đèn đã sáng chuẩn, hãy bật chế độ điều khiển chân cắm thật cho các bước sau:
- [ ] Kích hoạt GPIO thật:
```bash
export GPIOZERO_PIN_FACTORY=lgpio
```

- [ ] **Trường hợp 2 — Chưa lắp mạch LED:** Bật chế độ giả lập bằng phần mềm để code không báo lỗi khi chạy AI và camera *(lưu ý không đánh dấu là đã test xong phần cứng LED)*:

```bash
export GPIOZERO_PIN_FACTORY=mock
```

---

## Phút 20–24: Đăng ký khuôn mặt mới (trên màn hình Screen sharing)

> **Chuyển tab:** Từ bước này, hãy chuyển sang tab trình duyệt đang mở **Screen sharing** (màn hình desktop của Pi) và mở ứng dụng **Terminal** ngay trên màn hình đó. *(Mọi biến môi trường `export` và `venv` bạn gõ bên tab Remote shell trước đó đều không tự động nhảy sang cửa sổ Terminal mới này, nên ta cần khai báo lại).*

- [ ] **Trong Terminal trên màn hình desktop của Pi**, gõ cụm lệnh khởi tạo sau:

```bash
cd ~/IoT/pi4-edge-face-recognition
source venv/bin/activate
export CAM=0
export GPIOZERO_PIN_FACTORY=lgpio
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
printf 'Desktop=%s DISPLAY=%s WAYLAND_DISPLAY=%s\n' "$XDG_SESSION_TYPE" "$DISPLAY" "$WAYLAND_DISPLAY"
```
*(Nhớ sửa `CAM=0` thành đúng cổng camera bạn đã tìm được ở bước trước; và đổi `lgpio` thành `mock` nếu bạn không cắm mạch LED. Tuyệt đối không tự gõ `export DISPLAY=:0` mà hãy để Terminal tự nhận diện màn hình có sẵn. Ngoài ra, hãy chắc chắn không còn chương trình test camera nào đang chạy ngầm chiếm webcam).*

- [ ] Nhờ người cần đăng ký đứng vào trước webcam của Pi (nơi đủ ánh sáng, trong khung hình chỉ có đúng 1 người).
- [ ] **Chạy lệnh đăng ký khuôn mặt:**

```bash
python enroll.py --name "Violetta" --camera "$CAM" --samples 5
```

**Cách thao tác chụp mẫu:**
1. Chờ cửa sổ **SmartFace - Dang ky khuon mat** hiện lên trên màn hình desktop.
2. **Dùng chuột bấm (click) một cái vào cửa sổ hình ảnh camera** để chọn cửa sổ đó.
3. Khi thấy khuôn mặt hiện rõ, **bấm phím `s` từng lần một cho đến khi chụp đủ 5 mẫu** (giữa các lần bấm nên nghiêng nhẹ mặt sang trái/phải một chút để máy học đa dạng góc nhìn).
4. *(Lưu ý: Phải bấm phím `s` khi đang chọn cửa sổ hình ảnh camera, không phải gõ chữ `s` vào cửa sổ dòng lệnh Terminal. Nếu muốn thoát giữa chừng thì bấm phím `q`).*

- [ ] **Kiểm tra xem tên vừa đăng ký đã được lưu vào cơ sở dữ liệu (`faces.db`) chưa:**

```bash
python enroll.py --list
```
Kết quả in ra phải có tên `Violetta`.

> **Phương án dự phòng (nếu không mở được Screen sharing hoặc lỗi cửa sổ đồ họa):**
> Quay lại tab **Remote shell** (đã bật `venv` và đặt biến `CAM`), chạy lệnh dưới đây. Khi màn hình nhắc chụp từng mẫu, bạn chỉ cần nhấn phím **Enter** đủ 5 lần là xong:
> ```bash
> env -u DISPLAY -u WAYLAND_DISPLAY python enroll.py --name "Violetta" --camera "$CAM" --samples 5
> ```

---

## Phút 24–28: Chạy hệ thống chính và thử nghiệm 2 chế độ

- [ ] **Bước 1 — Chạy thử chế độ chỉ phát hiện khuôn mặt (tắt chống giả mạo `--no-pad`):**
Trong **Terminal trên màn hình Screen sharing**, chạy:

```bash
python -u run.py --no-pad --camera "$CAM"
```
- Chờ cửa sổ **Pi 4 Edge Face Recognition** hiện lên.
- Thử bước vào rồi bước ra khỏi khung hình: số lượng khuôn mặt đếm được và khung vuông quanh mặt phải thay đổi theo. *(Lưu ý: Chế độ `--no-pad` chủ yếu dùng để kiểm tra khả năng bắt khung hình và đếm mặt, chưa phải bước kiểm tra nhận diện tên).*
- Khi kiểm tra xong, **click chuột vào cửa sổ camera rồi bấm phím `q`** để tắt chương trình, chờ vài giây cho máy giải phóng camera hoàn toàn.

- [ ] **Bước 2 — Chạy chế độ đầy đủ (Nhận diện khuôn mặt + Chống giả mạo `--pad`) và lưu lại file log:**

```bash
set -o pipefail
python -u run.py --pad --camera "$CAM" 2>&1 | tee run-pad.log
```

Hãy quan sát cửa sổ camera: xem tên người, màu sắc của khung viền quanh mặt và chỉ số tốc độ khung hình (FPS). Dưới đây là bảng ý nghĩa các trạng thái trên màn hình và màu đèn LED tương ứng:

| Trạng thái hệ thống | Hiển thị trên cửa sổ Camera | Ý nghĩa | Màu đèn LED thật |
|---|---|---|---|
| **Đang kiểm tra PAD** | Khung **Vàng** | Đang thu thập đủ nhịp kiểm tra xem mặt thật hay giả | *(Giữ trạng thái chờ)* |
| `REAL_KNOWN` | Khung **Xanh lá** + Tên người | Xác nhận là **người thật** và **khớp tên** đã đăng ký | **Xanh** |
| `UNKNOWN` | Khung **Cam** + chữ `Unknown` | Là người thật nhưng **chưa có tên** trong dữ liệu | **Đỏ + Xanh (cùng sáng)** |
| `SPOOF` | Khung **Đỏ** + cảnh báo `SPOOF` | Phát hiện **giả mạo** (ảnh chụp, màn hình điện thoại...) | **Đỏ** |
| **Đang chờ người** | Không có khung | Không có khuôn mặt nào trong khung hình | **Tắt hết** |

*(Ghi chú: Con số phần trăm đi kèm bên cạnh tên người là điểm độ giống nhau nhân với 100 để dễ nhìn, không phải xác suất thống kê tuyệt đối. File `run-pad.log` chỉ lưu lại chữ in ra trên Terminal, không phải file quay video).*

- [ ] **Thử nghiệm thực tế:**
  1. Đưa **khuôn mặt thật** của người vừa đăng ký vào trước camera, giữ yên vài giây để hệ thống chốt kết quả PAD → kiểm tra xem có lên khung xanh kèm đúng tên không.
  2. Mở một **bức ảnh chụp khuôn mặt trên màn hình điện thoại** và giơ lên trước camera trong điều kiện ánh sáng tương tự, giữ vài giây → kiểm tra xem hệ thống có báo khung đỏ `SPOOF` không.
- [ ] **Ghi nhận trung thực kết quả:** Nếu máy nhận nhầm (ví dụ mặt thật nhưng lại báo `SPOOF`), bạn cứ ghi nhận đúng hiện trạng đó vào báo cáo, **không tự ý chỉnh sửa thông số ngưỡng (`FAS_LOGIT_THRESHOLD=-0.3730`)** ngay trong buổi chạy thử đầu tiên này.

**Mẹo điều khiển chương trình:**
- Khi đang xem trên Screen sharing: nhớ **click chuột vào cửa sổ hình ảnh camera** trước khi bấm phím `p` (để bật/tắt nhanh chế độ PAD) hoặc phím `q` (để thoát). Hoặc bạn có thể bấm tổ hợp `Ctrl+C` bên trong cửa sổ Terminal.
- **Phương án dự phòng nếu không dùng giao diện đồ họa (chạy qua Remote shell):**
  ```bash
  set -o pipefail
  python -u run.py --headless --pad --camera "$CAM" 2>&1 | tee run-pad.log
  ```
  *(Khi chạy `--headless`, chương trình sẽ in trạng thái dạng chữ liên tục ra màn hình, các phím `p` và `q` sẽ không có tác dụng — hãy dùng `Ctrl+C` khi muốn dừng. Tuyệt đối không mở chế độ có hình và chế độ `--headless` cùng một lúc trên cùng 1 chiếc webcam).*
- *Lưu ý về tốc độ hiển thị:* Chỉ số FPS in trên góc cửa sổ là tốc độ xử lý AI thực tế của Pi; còn việc bạn nhìn hình ảnh qua trình duyệt Screen sharing có mượt hay hơi khựng là do tốc độ truyền mạng Internet.

---

## Phút 28–30: Đóng ứng dụng, lưu kết quả và tổng kết

- [ ] Bấm phím `q` trên cửa sổ camera (hoặc `Ctrl+C` trong Terminal) để thoát hẳn ứng dụng, đảm bảo máy đã báo giải phóng xong camera và tắt toàn bộ đèn LED.
- [ ] **Lưu lại danh sách phiên bản thư viện đã cài đặt và kiểm tra 20 dòng log cuối cùng:**

```bash
python -m pip freeze > installed-on-pi.txt
tail -n 20 run-pad.log
```

### Bảng tổng kết nghiệm thu sau 30 phút
Hãy đánh dấu những mục bạn đã thực sự đạt được:
- [ ] Import thành công toàn bộ thư viện (`IMPORT OK`).
- [ ] Nạp thành công cả 3 model AI mặc định (`MODEL OK`).
- [ ] Webcam đọc được khung hình ảnh thực tế (`CAMERA OK`).
- [ ] Đã đăng ký và lưu thành công 1 người vào `faces.db`.
- [ ] Chế độ không PAD (`--no-pad`) đếm và bắt khung khuôn mặt thay đổi đúng khi có người ra/vào.
- [ ] Chế độ có PAD (`--pad`) chạy liên tục, hiện cửa sổ camera trên Screen sharing *(nếu chỉ chạy được `--headless` thì ghi rõ tại đây: __________ )*.
- [ ] Nhận diện đúng người đã đăng ký với khung màu xanh / `REAL_KNOWN` *(hoặc ghi lại lỗi nếu chưa đạt: __________ )*.
- [ ] Kết quả kiểm tra đèn LED *(ghi rõ "Đèn thật sáng đúng" hoặc "Chỉ mới chạy giả lập mock": __________ )*.
- [ ] Kết quả khi thử giơ ảnh giả mạo trên điện thoại: __________.

*(Lưu ý đánh giá: Nếu bạn mới chỉ chạy chế độ giả lập đèn `mock`, hoặc nạp được model nhưng webcam bị lỗi, hãy ghi nhận đúng những phần đã làm được chứ chưa kết luận là hoàn tất 100% hệ thống phần cứng. Tương tự, nếu ứng dụng chạy mượt nhưng giơ mặt thật vào mà PAD vẫn báo giả mạo `SPOOF`, nghĩa là phần cài đặt phần mềm đã thành công nhưng bước tinh chỉnh nhận diện thực tế vẫn cần xử lý tiếp).*

---

### Lệnh chạy nhanh cho những lần mở máy sau
Lần tới khi truy cập lại vào Raspberry Pi Connect, bạn chỉ cần mở **Terminal bên trong màn hình Screen sharing** và dán 6 dòng lệnh này để chạy ngay:

```bash
cd ~/IoT/pi4-edge-face-recognition
source venv/bin/activate
export CAM=0
export GPIOZERO_PIN_FACTORY=lgpio
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -u run.py --pad --camera "$CAM"
```
*(Nhớ đổi số `CAM=0` theo đúng cổng camera của bạn; đổi `lgpio` thành `mock` nếu không cắm mạch LED; và thêm cờ `--headless` vào dòng cuối nếu bạn chỉ chạy qua tab Remote shell. Hãy giữ nguyên cửa sổ Terminal này mở suốt quá trình demo).*

---

## Bảng tra cứu xử lý lỗi nhanh (Tối đa 2 phút cho mỗi lỗi)

Nếu gặp sự cố trong lúc chạy, hãy tra nhanh bảng dưới đây. **Nguyên tắc vàng:** Nếu loay hoay với 1 lỗi quá 2 phút mà chưa xong, hãy chụp/lưu lại thông báo lỗi đầu tiên để xử lý riêng — tuyệt đối không tự ý khởi động lại Pi (`reboot`), không chạy nâng cấp toàn bộ hệ điều hành hay sửa cấu hình mạng giữa buổi chạy.

| Dấu hiệu / Thông báo lỗi | Cách xử lý ngay |
|---|---|
| `No module named insightface` | Bạn quên bật môi trường ảo. Hãy gõ `source venv/bin/activate`. Nếu vẫn lỗi, chạy lại lệnh `pip install` ở mục Phút 03–12 và xem kỹ dòng báo lỗi đầu tiên. |
| `No matching distribution found` | Ghi lại tên gói bị lỗi kèm kết quả của 3 lệnh: `python --version`, `uname -m`, `python -m pip --version`. Kiểm tra xem đã nâng cấp `pip` chưa, sau đó dừng lại để chọn bản phù hợp (không tự hạ cấp OS hay ép máy biên dịch). |
| `externally-managed-environment` | Bạn đang cài nhầm vào Python gốc của hệ điều hành. Hãy gõ `source venv/bin/activate` trước khi dùng `pip`. Tuyệt đối không dùng `sudo pip` hay `--break-system-packages`. |
| Lỗi `Qt` hoặc `could not connect to display` | Đảm bảo bạn đang gõ lệnh trong ứng dụng **Terminal mở bên trong màn hình Screen sharing** (không phải tab Remote shell) và đã cài bản `opencv-python` đầy đủ. Không tự gõ `DISPLAY=:0`. Nếu sau 2 phút vẫn lỗi, hãy chuyển sang phương án dự phòng `--headless`. |
| Bấm phím `s`, `p`, `q` nhưng không thấy gì xảy ra | Bạn cần **click chuột vào bên trong cửa sổ hình ảnh camera** trước khi bấm phím (OpenCV chỉ nhận phím khi cửa sổ hình ảnh đang được chọn, không nhận phím gõ trong cửa sổ Terminal). |
| Hình ảnh trên trình duyệt bị giật dù chỉ số FPS vẫn cao | Đó là do độ trễ truyền hình ảnh của Screen sharing qua mạng Internet. Bạn có thể thu nhỏ bớt cửa sổ camera lại; khi báo cáo tốc độ xử lý AI, hãy lấy con số **FPS** hiện trên góc cửa sổ. |
| Không mở được camera / không đọc được khung hình | Chạy `v4l2-ctl --list-devices` để kiểm tra lại số `CAM`, đảm bảo không có cửa sổ/tiến trình cũ nào đang mở chiếm camera, và kiểm tra quyền truy cập `/dev/videoN` bằng lệnh `id`. |
| Báo lỗi `Permission denied` khi mở camera hoặc GPIO | Kiểm tra lệnh `id`. Nếu tài khoản của bạn chưa nằm trong nhóm `video` hoặc `gpio`, hãy chạy `sudo usermod -aG video,gpio "$USER"`, sau đó đóng tab shell Connect đi và mở lại (không cần reboot Pi), rồi bật lại `venv` và các biến `export`. |
| Không khởi tạo được GPIO / Đèn LED không sáng | Kiểm tra xem đã đặt `GPIOZERO_PIN_FACTORY=lgpio` chưa và rà lại dây cắm theo đúng số chân **BCM**. Nếu cần kíp, chuyển tạm sang `mock` để test xong phần mềm AI trước. |
| Máy tự động tải lại model `buffalo_s` ngoài ý muốn | Lưu lại thông báo lỗi gốc của SCRFD và kiểm tra dung lượng file bằng lệnh `ls -lh models/*.onnx`. Các model chuẩn đã nằm sẵn trong repo, việc máy tự tải model dự phòng có nghĩa là model chính đang gặp lỗi khi nạp. |
| Màn hình báo `UNKNOWN` liên tục dù đã đăng ký | Chạy `python enroll.py --list` xem đã có tên trong dữ liệu chưa; đứng ở nơi đủ sáng và chỉ để 1 khuôn mặt rõ ràng trước ống kính. Lưu lại log, không tự ý hạ ngưỡng nhận diện trong lần chạy đầu. |
| Bị rớt mạng hoặc lỡ tay đóng mất tab trình duyệt | Mở lại Connect, `cd` vào lại thư mục dự án, bật lại `venv` và các dòng `export`. Trước khi chạy lại app, nhớ gõ `pgrep -af '[p]ython.*run.py'` để kiểm tra xem lần chạy trước có còn kẹt ngầm không. |

---

## Căn cứ kỹ thuật & Giới hạn kiểm chứng

Kế hoạch này được xây dựng dựa trên việc đối chiếu trực tiếp mã nguồn của dự án (`requirements.txt`, `setup.sh`, `run.py`, `enroll.py`, module phát hiện khuôn mặt SCRFD, nhận diện ArcFace, chống giả mạo PAD và điều khiển LED) mà không cần sửa đổi bất kỳ dòng code nào của bạn. Vì các lệnh trên chưa được chạy thử trực tiếp trên chiếc Raspberry Pi thực tế của bạn, nên kết quả hoạt động của webcam, chân cắm GPIO và các gói thư viện cài sẵn vẫn cần bạn xác nhận thông qua các bước kiểm tra ở trên.

**Tài liệu tham khảo:**
- [Tài liệu chính thức Raspberry Pi Connect](https://www.raspberrypi.com/documentation/services/connect.html): Tính năng Screen sharing truyền màn hình desktop (Wayland) vào trình duyệt; cả Remote shell và Screen sharing đều hoạt động xuyên mạng Internet.
- [ONNX Runtime 1.23.0 trên PyPI](https://pypi.org/project/onnxruntime/1.23.0/): Đã hỗ trợ sẵn gói cài đặt (wheel) cho CPython 3.13 trên Linux ARM64 (`aarch64`).
- [InsightFace 2.1 trên PyPI](https://pypi.org/project/insightface/2.1/) & [setup.py của InsightFace](https://github.com/deepinsight/insightface/blob/master/python-package/setup.py): Cung cấp gói cài đặt thuần Python (`py3-none-any`), giúp cài nhanh phần lõi nhận diện mà không bị vướng bước biên dịch nhánh `face3d` như các bản cũ.
