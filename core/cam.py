import atexit
import threading
import time

_lock = threading.Lock()
_devs = None


def list_devices(force=False):
    """Cached probe. Never touches the camera unless force=True."""
    global _devs
    with _lock:
        if _devs is not None and not force:
            return _devs
        import cv2
        found = []
        for i in range(4):
            cap = None
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    ok, _ = cap.read()
                    if ok:
                        found.append(i)
            except Exception:
                pass
            finally:
                if cap is not None:
                    cap.release()
        _devs = found
        return found


def grab(idx=0, quality=80, width=1280, height=720, warm=4):
    """One-shot frame. Opens, reads, releases -> LED blips then goes off."""
    import cv2
    cap = None
    frame = None
    try:
        with _lock:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError('camera busy or missing')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for _ in range(warm):
                ok, f = cap.read()
                if ok:
                    frame = f
    finally:
        if cap is not None:
            cap.release()
    if frame is None:
        raise RuntimeError('no frame')
    ok, jpg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise RuntimeError('encode failed')
    return jpg.tobytes()


class Live:
    """Holds the camera open on purpose. LED stays on until stop()."""

    def __init__(self):
        self.on = False
        self.idx = 0
        self.q = 75
        self.fps = 15
        self._buf = None
        self._t = None

    def _loop(self):
        import cv2
        cap = None
        try:
            cap = cv2.VideoCapture(self.idx, cv2.CAP_DSHOW)
            if not cap.isOpened():
                self.on = False
                return
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            nxt = time.time()
            while self.on:
                ok, fr = cap.read()
                if ok:
                    ok, jpg = cv2.imencode('.jpg', fr, [cv2.IMWRITE_JPEG_QUALITY, self.q])
                    if ok:
                        self._buf = jpg.tobytes()
                nxt += 1.0 / self.fps
                d = nxt - time.time()
                time.sleep(d if d > 0 else 0)
                if d <= 0:
                    nxt = time.time()
        except Exception:
            self.on = False
        finally:
            if cap is not None:
                cap.release()
            self._buf = None

    def start(self, idx=0):
        if self.on and idx == self.idx:
            return False
        self.stop()
        self.idx = int(idx)
        self.on = True
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return True

    def stop(self):
        if not self.on and self._t is None:
            return
        self.on = False
        if self._t is not None:
            self._t.join(timeout=3)
            self._t = None
        self._buf = None

    def latest(self):
        return self._buf


LIVE = Live()
atexit.register(LIVE.stop)