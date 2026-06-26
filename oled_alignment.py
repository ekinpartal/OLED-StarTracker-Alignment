import cv2
import numpy as np
import time
import mss
import os

# --- AYARLAR (LABORATUVARDA BURAYI DÜZENLEYECEKSİNİZ) ---
OLED_WIDTH = 1920
OLED_HEIGHT = 1080
OLED_OFFSET_X = 1920  # OLED'in Windows ekran düzenindeki X başlangıcı
OLED_OFFSET_Y = 0

CAMERA_WIDTH = 1024
CAMERA_HEIGHT = 1024

SHARED_IMAGE_PATH = r"\\192.168.1.50\Kamera_Resimleri\kamera_output.bmp"

# --- KALİBRASYON İÇ AYARLARI ---
BOARD_COLS = 7
BOARD_ROWS = 5
SQUARE_SIZE = 60
P_GAIN_X = 0.5
P_GAIN_Y = 0.5
TOLERANCE_PX = 1.0
MAX_SHIFT = 50

# --- FONKSİYONLAR ---
def generate_chessboard(offset_x, offset_y, width, height, cols, rows, square_size):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    board_w = (cols + 1) * square_size
    board_h = (rows + 1) * square_size
    start_x = (width - board_w) // 2 + int(offset_x)
    start_y = (height - board_h) // 2 + int(offset_y)
    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 0:
                x1 = max(0, min(width,  start_x + c * square_size))
                y1 = max(0, min(height, start_y + r * square_size))
                x2 = max(0, min(width,  x1 + square_size))
                y2 = max(0, min(height, y1 + square_size))
                if x2 > x1 and y2 > y1:
                    img[y1:y2, x1:x2] = (255, 255, 255)
    return img

def shift_image(image, offset_x, offset_y):
    h, w = image.shape[:2]
    M = np.float32([[1, 0, int(offset_x)], [0, 1, int(offset_y)]])
    return cv2.warpAffine(image, M, (w, h), borderValue=(0, 0, 0))

def detect_pattern(frame_gray, cols, rows):
    found, corners = cv2.findChessboardCorners(frame_gray, (cols, rows), None)
    if found:
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners = cv2.cornerSubPix(frame_gray, corners, (11, 11), (-1, -1), criteria)
        center_x = np.mean(corners[:, 0, 0])
        center_y = np.mean(corners[:, 0, 1])
        return True, center_x, center_y
    return False, 0, 0

def wait_for_file_ready(filepath, timeout=5.0):
    start_time = time.time()
    last_size = -1
    while time.time() - start_time < timeout:
        try:
            size = os.path.getsize(filepath)
            if size == last_size and size > 0:
                return True
            last_size = size
        except Exception:
            pass
        time.sleep(0.1)
    return False

def get_image_from_network(filepath):
    if not wait_for_file_ready(filepath):
        print("[HATA] Dosya tam olarak okunamadı veya bozuk!")
        return None
    try:
        frame = cv2.imread(filepath)
        if frame is None:
            return None
        if len(frame.shape) == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame
    except Exception as e:
        print(f"Resim okuma hatası: {e}")
        return None

def main():
    print("--- YILDIZİZLER: Wi-Fi AĞ PAYLAŞIMLI OTOMATİK HİZALAMA ---")

    camera_center_x = CAMERA_WIDTH / 2.0
    camera_center_y = CAMERA_HEIGHT / 2.0

    window_name = "OLED_Display"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(window_name, OLED_OFFSET_X, OLED_OFFSET_Y)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    offset_x = 0.0
    offset_y = 0.0
    mode = "CALIBRATION"
    last_modified_time = 0

    print("\n[AŞAMA 1] KALİBRASYON BAŞLADI!")
    print(f"Kod şu dosyayı bekliyor: {SHARED_IMAGE_PATH}")
    print("Lütfen 3. Bilgisayara gidip 'make 5 3' komutuyla fotoğraf çekin.")

    sct = mss.mss()
    monitor_1 = sct.monitors[1]

    while True:
        key = 0xFF  # Her iterasyonda sıfırla — tanımsız key hatasını önler

        if mode == "CALIBRATION":
            pattern_img = generate_chessboard(
                offset_x, offset_y, OLED_WIDTH, OLED_HEIGHT,
                BOARD_COLS, BOARD_ROWS, SQUARE_SIZE
            )
            cv2.imshow(window_name, pattern_img)
            key = cv2.waitKey(100) & 0xFF

            if os.path.exists(SHARED_IMAGE_PATH):
                current_modified_time = os.path.getmtime(SHARED_IMAGE_PATH)

                if current_modified_time > last_modified_time:
                    print("\n[BİLGİ] Yeni kamera görüntüsü tespit edildi! Okunuyor...")
                    frame_gray = get_image_from_network(SHARED_IMAGE_PATH)
                    last_modified_time = current_modified_time

                    if frame_gray is not None:
                        found, detected_x, detected_y = detect_pattern(
                            frame_gray, BOARD_COLS, BOARD_ROWS
                        )
                        if found:
                            error_x = camera_center_x - detected_x
                            error_y = camera_center_y - detected_y
                            print(f"Tespit: ({detected_x:.1f}, {detected_y:.1f}) | "
                                  f"Hata: X={error_x:.2f}, Y={error_y:.2f}")

                            if abs(error_x) < TOLERANCE_PX and abs(error_y) < TOLERANCE_PX:
                                print("\n✅ MÜKEMMEL HİZALAMA SAĞLANDI!")
                                print(f"Fiziksel Sapma: X={offset_x:.2f}, Y={offset_y:.2f}")
                                print("CANLI AYNA moduna geçiyor...")
                                mode = "MIRROR"
                                time.sleep(2)
                            else:
                                shift_x = np.clip(error_x * P_GAIN_X, -MAX_SHIFT, MAX_SHIFT)
                                shift_y = np.clip(error_y * P_GAIN_Y, -MAX_SHIFT, MAX_SHIFT)
                                offset_x += shift_x
                                offset_y += shift_y
                                print(f"Yeni Offset → X:{offset_x:.2f}, Y:{offset_y:.2f}")
                                print("TEKRAR 'make 5 3' yazıp fotoğraf çekin!")
                        else:
                            print("[UYARI] Resimde satranç tahtası bulunamadı!")

        elif mode == "MIRROR":
            sct_img = sct.grab(monitor_1)
            desktop_frame = cv2.cvtColor(np.array(sct_img), cv2.COLOR_BGRA2BGR)
            desktop_frame = cv2.resize(desktop_frame, (OLED_WIDTH, OLED_HEIGHT))
            shifted = shift_image(desktop_frame, offset_x, offset_y)
            cv2.imshow(window_name, shifted)
            key = cv2.waitKey(10) & 0xFF

        if key == ord('q') or key == 27:  # Q veya ESC ile çık
            print("\nProgram kapatılıyor...")
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
