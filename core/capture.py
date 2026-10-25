import io
import threading
import time

import mss
import numpy as np
from PIL import Image

TILE = 48
THRESH = 3
KEY_EVERY = 120
FULL_RATIO = 0.40
MAX_RECTS = 14
MAX_RECT_W = 1024


def _sig(arr, tile=TILE):
    h, w = arr.shape[:2]
    ph, pw = (-h) % tile, (-w) % tile
    if ph or pw:
        arr = np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode='edge')
    th, tw = arr.shape[0] // tile, arr.shape[1] // tile
    return arr.reshape(th, tile, tw, tile, 3).mean(axis=(1, 3))


def _runs(mask):
    """bool grid -> list of merged [y0,x0,y1,x1] rects in tile units."""
    th, tw = mask.shape
    rows = []
    for y in range(th):
        xs = np.flatnonzero(mask[y])
        if xs.size == 0:
            continue
        start = prev = xs[0]
        for x in xs[1:]:
            if x != prev + 1:
                rows.append([y, start, y, prev])
                start = x
            prev = x
        rows.append([y, start, y, prev])

    merged = []
    for r in rows:
        for m in merged:
            if r[0] == m[2] + 1 and not (r[3] < m[1] or r[1] > m[3]):
                m[2] = r[2]
                m[1] = min(m[1], r[1])
                m[3] = max(m[3], r[3])
                break
        else:
            merged.append(list(r))
    return merged


class Streamer:
    def __init__(self):
        self.fps = 30
        self.q = 60
        self.scale = 1.0
        self.mon = 1
        self.on = False
        self.out = None
        self.prev = None
        self.n = 0
        self.paused = False
        self._t = None

    def _loop(self):
        buf = io.BytesIO()
        nxt = time.time()
        with mss.mss() as sct:
            while self.on:
                if self.paused:
                    time.sleep(0.06)
                    nxt = time.time()
                    continue

                t0 = time.time()
                try:
                    raw = sct.grab(sct.monitors[self.mon])
                    a = np.frombuffer(raw.raw, dtype=np.uint8).reshape(raw.height, raw.width, 4)
                    img = Image.fromarray(np.ascontiguousarray(a[:, :, 2::-1]))
                    if self.scale != 1:
                        img = img.resize((max(2, int(img.width * self.scale)),
                                          max(2, int(img.height * self.scale))), Image.BILINEAR)

                    sig = _sig(np.asarray(img))
                    key = (self.prev is None or self.prev.shape != sig.shape
                           or self.n % KEY_EVERY == 0)
                    changed = (np.ones(sig.shape[:2], dtype=bool) if key
                               else np.abs(sig - self.prev).max(axis=2) > THRESH)
                    self.n += 1

                    if changed.any() and self.out:
                        ratio = changed.sum() / changed.size
                        if key or ratio > FULL_RATIO:
                            rects = [(0, 0, img.width, img.height)]
                        else:
                            rects = []
                            for y0, x0, y1, x1 in _runs(changed):
                                px0, py0 = x0 * TILE, y0 * TILE
                                px1 = min((x1 + 1) * TILE, img.width)
                                py1 = min((y1 + 1) * TILE, img.height)
                                for sx in range(px0, px1, MAX_RECT_W):
                                    rects.append((sx, py0, min(sx + MAX_RECT_W, px1), py1))
                            if len(rects) > MAX_RECTS:
                                rects = [(0, 0, img.width, img.height)]

                        ok = True
                        for x0, y0, x1, y1 in rects:
                            buf.seek(0)
                            buf.truncate()
                            img.crop((x0, y0, x1, y1)).save(
                                buf, 'JPEG', quality=self.q, subsampling=2, optimize=False)
                            ok = self.out(x0, y0, x1 - x0, y1 - y0, buf.getvalue(),
                                          img.width, img.height, key) and ok
                        if ok:
                            self.prev = sig
                except Exception:
                    pass

                nxt += 1.0 / self.fps
                d = nxt - time.time()
                if d > 0:
                    time.sleep(d)
                else:
                    nxt = time.time()

    def start(self):
        if self.on:
            return
        self.on, self.prev, self.n = True, None, 0
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self):
        self.on = False
        if self._t is not None:
            self._t.join(timeout=2)
            self._t = None

    def snap(self, mon=None):
        with mss.mss() as sct:
            raw = sct.grab(sct.monitors[mon or self.mon])
            return Image.frombytes('RGB', raw.size, raw.bgra, 'raw', 'BGRX')

    def snap_bytes(self, mon=None):
        b = io.BytesIO()
        self.snap(mon).save(b, 'PNG')
        return b.getvalue()


STREAM = Streamer()


def monitors():
    with mss.mss() as sct:
        return [{'i': i, 'w': m['width'], 'h': m['height']}
                for i, m in enumerate(sct.monitors) if i]