"""
Bot Battle Royale por reconhecimento de imagem.

Ciclo:  Lobby (clica JOGAR) -> espera o onibus -> pula no ponto do mapa ->
        fica planando -> no chao: anda/pula/picareta/corre/olha pra tras ->
        quando o TIME INTEIRO morre: sai da partida -> volta pro lobby -> repete.

Os "modelos" sao recortes de print que voce tira do jogo (pasta modelos/).
"""
import math
import os
import random
import threading
import time

import cv2
import numpy as np

import recorder as rec

BASE = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE, "modelos")
PRINTS_DIR = os.path.join(BASE, "capturas")
SCALE = 0.5   # compara as imagens em meia resolucao (mais rapido)

# chave, nome, dica, obrigatorio
SLOTS = [
    ("jogar", "Botão JOGAR (lobby)", "o botão JOGAR do lobby", True),
    ("onibus", "No ônibus", "algo que só aparece no ônibus (ex.: aviso de 'Pular')", True),
    ("onibus2", "No ônibus (banner da gorjeta)", "opcional: o banner 'GOSTOU DA CONDUÇÃO? DEIXE UMA GORJETA'", False),
    ("icone_onibus", "Ícone do ônibus no mapa", "opcional: o ícone do ônibus com o mapa aberto (M)", False),
    ("no_ar", "Caindo / planando", "opcional: algo que só aparece no ar (ex.: altímetro)", False),
    ("time_morto", "Time inteiro eliminado (extra)", "opcional: o painel do time já é checado pelas cores "
                   "(sem barra verde + nomes rosa = time morto). Use isto só no modo Solo.", False),
    ("sair", "Botão Sair / Voltar ao lobby", "botão que tira você da partida (precisa deste OU do 'Sair da partida' do ESC)", False),
    ("menu_tab", "Aba ☰ (3 barrinhas) do menu ESC", "o ícone das 3 barrinhas no topo do menu do ESC", False),
    ("menu_engrenagem", "Engrenagem ⚙ do menu ESC", "a engrenagem do topo do ESC (clica ao lado, no ☰)", False),
    ("esc_sair", "'Voltar ao Lobby' no menu ESC", "o botão 'Voltar ao Lobby' (aba das 3 barrinhas do ESC)", False),
    ("confirmar", "Confirmar / Continuar", "opcional: confirmação de saída ou tela de resumo", False),
]

SCAN = {"W": 0x11, "A": 0x1E, "S": 0x1F, "D": 0x20, "SPACE": 0x39, "SHIFT": 0x2A,
        "CTRL": 0x1D, "ESC": 0x01, "M": 0x32, "E": 0x12,
        "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06}


PANEL_BOX = [0.0, 0.60, 0.25, 0.95]   # painel do time (canto inferior esquerdo), fracao da tela
PINK_MIN = 300                        # minimo de pixels rosa (nomes de eliminados)
_LINE_KERNEL = np.ones((1, 30), np.uint8)


def team_panel_state(bgr):
    """(tem_barra_verde, pixels_rosa) no painel do time.
    Barra de vida verde = linha horizontal verde de 30+ px. Nome de eliminado = rosa."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = ((h >= 35) & (h <= 85) & (s >= 120) & (v >= 170)).astype(np.uint8)
    pink = ((h >= 150) | (h <= 5)) & (s >= 110) & (v >= 170)
    has_line = bool(cv2.erode(green, _LINE_KERNEL).any())
    return has_line, int(pink.sum())


def imread(path, flags=cv2.IMREAD_COLOR):
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, flags) if data.size else None


def imwrite(path, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(path)
    return ok


class Vision:
    def __init__(self):
        self._local = threading.local()
        self._cache = {}

    def _sct(self):
        s = getattr(self._local, "sct", None)
        if s is None:
            import mss
            s = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
            self._local.sct = s
        return s

    def grab_bgr(self):
        s = self._sct()
        mon = s.monitors[1]
        return cv2.cvtColor(np.asarray(s.grab(mon)), cv2.COLOR_BGRA2BGR), mon["left"], mon["top"]

    def frame(self):
        s = self._sct()
        mon = s.monitors[1]
        g = cv2.cvtColor(np.asarray(s.grab(mon)), cv2.COLOR_BGRA2GRAY)
        g = cv2.resize(g, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
        return g, mon["left"], mon["top"]

    def grab_rel(self, box):
        """print de um pedaco da tela; box = [x0, y0, x1, y1] em fracao da tela (0..1)"""
        s = self._sct()
        mon = s.monitors[1]
        W, H = mon["width"], mon["height"]
        reg = {"left": mon["left"] + int(W * box[0]), "top": mon["top"] + int(H * box[1]),
               "width": max(1, int(W * (box[2] - box[0]))), "height": max(1, int(H * (box[3] - box[1])))}
        return cv2.cvtColor(np.asarray(s.grab(reg)), cv2.COLOR_BGRA2BGR)

    @staticmethod
    def path(key):
        return os.path.join(MODELS_DIR, key + ".png")

    def has(self, key):
        return os.path.exists(self.path(key))

    def _tpl(self, key):
        p = self.path(key)
        if not os.path.exists(p):
            return None
        m = os.path.getmtime(p)
        c = self._cache.get(key)
        if c and c[0] == m:
            return c[1]
        t = imread(p, cv2.IMREAD_GRAYSCALE)
        if t is None:
            return None
        t = cv2.resize(t, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
        self._cache[key] = (m, t)
        return t

    def score(self, key, frame):
        """Retorna (x, y, score) do melhor ponto, ou None se nao houver modelo."""
        t = self._tpl(key)
        if t is None:
            return None
        g, ox, oy = frame
        if t.shape[0] > g.shape[0] or t.shape[1] > g.shape[1] or t.shape[0] < 4 or t.shape[1] < 4:
            return None
        r = cv2.matchTemplate(g, t, cv2.TM_CCOEFF_NORMED)
        _, mx, _, loc = cv2.minMaxLoc(r)
        x = ox + int((loc[0] + t.shape[1] / 2) / SCALE)
        y = oy + int((loc[1] + t.shape[0] / 2) / SCALE)
        return x, y, (0.0 if math.isnan(mx) else float(mx))

    def find(self, key, frame, thr):
        r = self.score(key, frame)
        return r if r and r[2] >= thr else None


class Stop(Exception):
    pass


class BRBot:
    def __init__(self, cfg, log, focused):
        self.cfg = cfg
        self.log = log
        self.focused = focused
        self.vision = Vision()
        self.running = threading.Event()
        self.state = "Parado"
        self.matches = 0
        self.held = set()
        self.thread = None
        self.saw_alive = False
        self.last_quit = 0.0

    # ---------------------------------------------------------- controle
    def start(self):
        if self.running.is_set():
            return
        missing = [n for k, n, _, req in SLOTS if req and not self.vision.has(k)]
        if not (self.vision.has("sair") or self.vision.has("esc_sair")):
            missing.append("Botão Sair OU 'Sair da partida' do ESC")
        if missing:
            self.log("[BR] Faltam modelos: " + ", ".join(missing))
            return
        self.running.set()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.log("[BR] Bot INICIADO")

    def stop(self):
        if self.running.is_set():
            self.running.clear()
            self._release()
            self.log("[BR] Bot PARADO")
        self.state = "Parado"

    def _set(self, s):
        self.state = s
        self.log(f"[BR] {s}")

    # ---------------------------------------------------------- input
    def _key(self, k, down):
        rec._key(SCAN[k], 0, down)
        (self.held.add if down else self.held.discard)(k)

    def _release(self):
        for k in list(self.held):
            rec._key(SCAN[k], 0, False)
        self.held.clear()

    def tap(self, k, hold=0.08):
        self._key(k, True)
        try:
            self.wait(hold)
        finally:
            self._key(k, False)

    def hold(self, keys, secs):
        for k in keys:
            self._key(k, True)
        try:
            self.wait(secs)
        finally:
            for k in keys:
                self._key(k, False)

    def lclick(self, n=1, gap=0.35):
        for _ in range(n):
            rec._mouse(rec.BTN[("L", 1)])
            self.wait(0.06)
            rec._mouse(rec.BTN[("L", 0)])
            self.wait(gap)

    def click_at(self, pos):
        rec.user32.SetCursorPos(int(pos[0]), int(pos[1]))
        self.wait(0.1)
        self.lclick(1, 0.1)

    def turn(self, px, secs=0.3):
        steps = 20
        for i in range(steps):
            rec._mouse(rec.MOVE, int(px / steps), 0)
            self.wait(secs / steps)

    def wait(self, secs):
        end = time.time() + secs
        while True:
            if not self.running.is_set():
                raise Stop
            if not self.focused():
                keys = set(self.held)
                self._release()
                paused = time.time()
                while not self.focused():
                    if not self.running.is_set():
                        raise Stop
                    time.sleep(0.2)
                for k in keys:
                    self._key(k, True)
                end += time.time() - paused
            rem = end - time.time()
            if rem <= 0:
                return
            time.sleep(min(rem, 0.05))

    # ---------------------------------------------------------- visao
    def frame(self):
        return self.vision.frame()

    def seen(self, key, frame=None):
        return self.vision.find(key, frame or self.frame(), float(self.cfg.get("limiar", 0.8)))

    def team_dead(self, frame=None):
        if self.seen("time_morto", frame):
            return True
        if not self.cfg.get("usar_painel_time", True):
            return False
        box = self.cfg.get("painel_time", PANEL_BOX)
        line, pink = team_panel_state(self.vision.grab_rel(box))
        if line:
            if not self.saw_alive:
                self.log("[BR] Painel do time encontrado (barras verdes)")
            self.saw_alive = True
            return False
        if pink < PINK_MIN:
            return False
        if not self.saw_alive:
            # nunca vimos as barras verdes nesta partida: nao confia nas cores
            return False
        # confirma 4 vezes seguidas, 1 s entre elas
        for _ in range(3):
            self.wait(1.0)
            line, pink = team_panel_state(self.vision.grab_rel(box))
            if line or pink < PINK_MIN:
                return False
        self.log(f"[BR] Painel do time: nenhuma barra verde, nomes rosa ({pink}px) = time todo morto")
        self._debug_shot("time_morto")
        return True

    def _debug_shot(self, tag):
        try:
            d = os.path.join(BASE, "debug")
            os.makedirs(d, exist_ok=True)
            img, _, _ = self.vision.grab_bgr()
            imwrite(os.path.join(d, time.strftime(f"{tag}_%H%M%S.png")), img)
        except Exception:
            pass

    # ---------------------------------------------------------- ciclo
    def _loop(self):
        rec.winmm.timeBeginPeriod(1)            # sleep com precisao de 1 ms
        while self.running.is_set():
            try:
                self._cycle()
            except Stop:
                break
            except Exception as e:
                self.log(f"[BR] Erro: {e!r}")
                time.sleep(2)
        self._release()
        rec.winmm.timeEndPeriod(1)

    def _cycle(self):
        # 1) lobby
        self._set("Lobby: procurando JOGAR")
        clicked = 0.0
        while True:
            f = self.frame()
            if self.seen("onibus", f) or self.seen("onibus2", f):
                break
            # no lobby/fila/carregamento NAO checa o painel por cores (dava falso positivo)
            for key in ("confirmar", "sair"):          # telas de resumo que sobraram
                p = self.seen(key, f)
                if p:
                    self.click_at(p)
                    self.wait(1.5)
                    break
            else:
                p = self.seen("jogar", f)
                left = float(self.cfg.get("espera_partida", 60)) - (time.time() - self.last_quit)
                if p and left > 0:
                    self.state = f"Lobby: esperando {left:.0f}s pra próxima partida"
                    self.wait(1)
                    continue
                if p and time.time() - clicked > 10:
                    self.click_at(p)
                    clicked = time.time()
                    self._set("Na fila: esperando a partida começar")
            self.wait(1)

        # 2) onibus
        self.matches += 1
        self.saw_alive = False
        self._set(f"No ônibus (partida #{self.matches})")
        self._debug_shot("onibus")
        self._bus_jump()

        # 3) no ar
        self._set("Pulou: planando")
        if self._air():
            # 4) no chao
            self._set("No chão: anti-AFK em movimento")
            self._ground()
        # 5) time morreu
        self._quit()

    def _bus_jump(self):
        c = self.cfg
        self.wait(float(c.get("espera_onibus", 4)))
        target = c.get("alvo_mapa")
        start = time.time()
        if self.vision.has("icone_onibus") and target:
            tx, ty = target
            raio = float(c.get("raio_alvo", 60))
            best = None
            while time.time() - start < float(c.get("pulo_max", 70)):
                self.tap("M")
                self.wait(0.8)
                p = self.vision.find("icone_onibus", self.frame(), float(c.get("limiar", 0.8)) - 0.1)
                self.tap("M")
                if p:
                    d = math.hypot(p[0] - tx, p[1] - ty)
                    self.log(f"[BR] ônibus a {d:.0f}px do alvo")
                    if d <= raio:
                        self.log("[BR] Em cima do alvo: pulando")
                        break
                    if best is not None and d > best + raio * 0.5:
                        self.log("[BR] Ônibus passou do ponto mais perto: pulando")
                        break
                    best = d if best is None else min(best, d)
                self.wait(1.0)
        else:
            self.wait(max(0.0, float(c.get("pulo_segundos", 25)) - float(c.get("espera_onibus", 4))))
        self.tap("SPACE")
        self.wait(0.6)
        self.tap("SPACE")

    def _air_wiggle(self, secs):
        """mexe no ar sem mergulhar: olha em volta e da toques curtos nas teclas"""
        end = time.time() + secs
        while time.time() < end:
            ev, T = [], random.uniform(0.8, 1.6)
            choice = random.random()
            if choice < 0.35:
                self.k(ev, random.choice("AD"), 0, random.uniform(0.25, 0.7))
            elif choice < 0.55:
                self.k(ev, "W", 0, random.uniform(0.2, 0.5))
                self.k(ev, random.choice("AD"), 0.1, random.uniform(0.3, 0.6))
            elif choice < 0.7:
                self.k(ev, "S", 0, random.uniform(0.2, 0.5))
            self.mouse(ev, 0, T, random.choice([1, -1]) * random.randint(60, 350), random.randint(-60, 60))
            self.run_timeline(ev)
            self.wait(random.uniform(0.05, 0.3))

    def _air(self):
        """Planando, mexendo no ar. Retorna False se o time morreu no ar."""
        start = time.time()
        if self.vision.has("no_ar"):
            self._air_wiggle(5)
            gone = 0
            while time.time() - start < 180:
                f = self.frame()
                if self.team_dead(f):
                    return False
                gone = 0 if self.seen("no_ar", f) else gone + 1
                if gone >= 3:
                    break
                self._air_wiggle(1.5)
        else:
            last_check = time.time()
            while time.time() - start < float(self.cfg.get("tempo_queda", 80)):
                if time.time() - last_check > 6:
                    last_check = time.time()
                    if self.team_dead():
                        return False
                self._air_wiggle(2)
        return True

    # ---------------------------------------------------------- combos "humanos"
    # Cada combo e uma linha do tempo: varias teclas seguradas ao mesmo tempo,
    # mouse virando em curva suave, cliques no meio - tudo com variacao aleatoria.
    def run_timeline(self, ev):
        ev.sort(key=lambda e: e[0])
        last = 0.0
        try:
            for t, fn in ev:
                if t > last:
                    self.wait(t - last)
                    last = t
                fn()
        finally:
            self._release()

    def _down(self, k):
        return lambda: self._key(k, True)

    def _up(self, k):
        return lambda: self._key(k, False)

    def _click(self, down):
        return lambda: rec._mouse(rec.BTN[("L", down)])

    def k(self, ev, key, t0, t1):
        """segura `key` de t0 ate t1 (com jitter)"""
        t0 += random.uniform(0, 0.06)
        t1 += random.uniform(-0.04, 0.06)
        ev += [(max(0.0, t0), self._down(key)), (max(t0 + 0.05, t1), self._up(key))]

    def tapk(self, ev, key, t):
        self.k(ev, key, t, t + random.uniform(0.06, 0.12))

    def clicks(self, ev, t0, n, gap=(0.28, 0.45)):
        """picareta: as vezes cliques soltos, as vezes segura o botao (golpes continuos)"""
        t = t0
        if random.random() < 0.6:
            for _ in range(random.randint(1, 2)):
                hold = random.uniform(0.9, 2.4)
                ev += [(t, self._click(1)), (t + hold, self._click(0))]
                t += hold + random.uniform(0.15, 0.4)
            return t
        for _ in range(n):
            ev += [(t, self._click(1)), (t + random.uniform(0.05, 0.11), self._click(0))]
            t += random.uniform(*gap)
        return t

    @staticmethod
    def _noise():
        """ruido suave (soma de senos com fases aleatorias) - tremida continua, nao aleatoria a cada passo"""
        comps = [(random.uniform(0.5, 1.5), random.uniform(1.5, 4.0), random.uniform(0, 6.28)) for _ in range(3)]
        return lambda t: sum(a * math.sin(f * 6.28 * t + ph) for a, f, ph in comps)

    def mouse(self, ev, t0, t1, dx, dy=0):
        """vira a camera como uma mao: curva leve, velocidade irregular,
        passa um pouco do ponto e corrige, com tremida suave."""
        dur = max(0.08, t1 - t0)
        over = random.uniform(1.03, 1.10) if abs(dx) > 150 and random.random() < 0.7 else 1.0
        main = dur * (random.uniform(0.75, 0.88) if over > 1 else 1.0)
        bend = random.uniform(-0.12, 0.12) * abs(dx)        # curva pra cima/baixo no meio do movimento
        skew = random.uniform(0.35, 0.65)                    # pico de velocidade antes ou depois do meio
        nx, ny = self._noise(), self._noise()
        amp = min(2.5, 0.6 + abs(dx) / 400)

        def ease(p):                                         # aceleracao assimetrica
            if p < skew:
                q = p / skew
                return skew * q * q
            q = (p - skew) / (1 - skew)
            return skew + (1 - skew) * (1 - (1 - q) * (1 - q))

        pts, t = [], 0.0
        while t < dur:
            t = min(dur, t + random.uniform(0.008, 0.016))  # intervalo irregular entre movimentos
            if t <= main:
                p = t / main
                e = ease(p)
                x = dx * over * e
                y = dy * e + bend * math.sin(math.pi * p)
            else:                                            # correcao do overshoot
                q = (t - main) / (dur - main)
                c = q * q * (3 - 2 * q)
                x = dx * (over + (1 - over) * c)
                y = dy
            pts.append((t, x + amp * nx(t), y + amp * 0.7 * ny(t)))
        if pts:                                              # termina exatamente no alvo
            pts[-1] = (pts[-1][0], float(dx), float(dy))
        prev_x = prev_y = 0
        for tt, x, y in pts:
            mx, my = int(round(x)) - prev_x, int(round(y)) - prev_y
            if mx or my:
                prev_x += mx; prev_y += my
                ev.append((t0 + tt, (lambda a, b: lambda: rec._mouse(rec.MOVE, a, b))(mx, my)))
            if random.random() < 0.03:                       # micro pausa
                t0 += random.uniform(0.02, 0.06)

    def _combos(self):
        g = int(self.cfg.get("giro_180", 1200))
        sd = lambda: random.choice([1, -1])
        L, R = random.sample(["A", "D"], 2)            # lado inicial aleatorio

        def frente_zigue():                              # W+D, depois W+A
            ev, T = [], random.uniform(2.0, 3.5)
            self.k(ev, "W", 0, T)
            self.k(ev, R, 0.1, T * 0.5)
            self.k(ev, L, T * 0.5 + 0.05, T)
            self.mouse(ev, 0.2, T, sd() * random.randint(60, 220), random.randint(-15, 15))
            return ev

        def tras_lado_pulo():                            # S+D+espaco
            ev, T = [], random.uniform(1.2, 2.2)
            self.k(ev, "S", 0, T)
            self.k(ev, R, 0.15, T)
            self.tapk(ev, "SPACE", T * random.uniform(0.3, 0.6))
            self.mouse(ev, 0, T, sd() * random.randint(40, 140))
            return ev

        def gira_picareta():                             # vira o mouse batendo de picareta
            ev = []
            self.tapk(ev, "1", 0)
            T = random.uniform(1.2, 2.0)
            self.mouse(ev, 0.15, T, sd() * random.randint(int(g * 0.3), int(g * 0.7)), random.randint(-40, 40))
            self.clicks(ev, 0.3, random.randint(3, 5))
            return ev

        def pula_picareta_andando():                     # W + pulo + picareta
            ev, T = [], random.uniform(1.8, 3.0)
            self.tapk(ev, "1", 0)
            self.k(ev, "W", 0.05, T)
            self.k(ev, random.choice("AD"), T * 0.3, T * 0.7)
            for t in (0.3, T * 0.6):
                self.tapk(ev, "SPACE", t)
            self.clicks(ev, 0.4, random.randint(2, 4))
            self.mouse(ev, 0.2, T, sd() * random.randint(50, 180))
            return ev

        def correr_cansar():                             # W+SHIFT ate a estamina acabar, zig-zag e pulos
            ev, T = [], random.uniform(4.5, 7.0)
            self.k(ev, "W", 0, T)
            self.k(ev, "SHIFT", 0.05, T)
            t, side = 0.4, R
            while t < T - 0.6:
                d = random.uniform(0.4, 0.9)
                self.k(ev, side, t, t + d)
                if random.random() < 0.5:
                    self.tapk(ev, "SPACE", t + d * 0.5)
                side = L if side == R else R
                t += d + random.uniform(0.1, 0.4)
            self.mouse(ev, 0.3, T, sd() * random.randint(80, 300), random.randint(-20, 20))
            return ev

        def olha_tras_volta():                           # anda pra tras, olha pra tras, volta
            ev = []
            t1 = random.uniform(0.8, 1.4)
            self.k(ev, "S", 0, t1)
            self.k(ev, L, 0.2, t1)
            s = sd()
            self.mouse(ev, t1 - 0.2, t1 + 0.45, s * g, random.randint(-20, 20))
            t2 = t1 + 0.5 + random.uniform(1.0, 1.8)
            self.k(ev, "W", t1 + 0.4, t2)
            self.tapk(ev, "SPACE", t1 + 0.9)
            self.mouse(ev, t2 - 0.1, t2 + 0.5, -s * g)
            return ev

        def lado_pulo_mira():                            # A ou D + pulo + virando
            ev, T = [], random.uniform(1.0, 1.8)
            self.k(ev, R, 0, T)
            self.k(ev, "W", T * 0.3, T)
            self.tapk(ev, "SPACE", T * 0.4)
            self.mouse(ev, 0, T, sd() * random.randint(100, 350), random.randint(-30, 30))
            self.clicks(ev, T * 0.5, random.randint(1, 2))
            return ev

        def troca_armas():                               # anda e fica trocando 1..5 + pulo
            ev, T = [], random.uniform(1.5, 2.8)
            self.k(ev, random.choice(["W", "S"]), 0, T)
            self.k(ev, R, T * 0.2, T * 0.6)
            t = 0.1
            while t < T:
                self.tapk(ev, random.choice("12345"), t)
                t += random.uniform(0.2, 0.5)
            self.tapk(ev, "SPACE", T * random.uniform(0.3, 0.8))
            self.mouse(ev, 0, T, sd() * random.randint(40, 160), random.randint(-15, 15))
            return ev

        def tras_pulando():                              # S + espaco + troca de arma
            ev, T = [], random.uniform(1.0, 1.8)
            self.k(ev, "S", 0, T)
            self.k(ev, random.choice("AD"), T * 0.4, T)
            self.tapk(ev, "SPACE", 0.2)
            self.tapk(ev, random.choice("2345"), T * 0.5)
            self.tapk(ev, "1", T - 0.1)
            return ev

        def marcar_mapa():                               # abre o mapa, marca um ponto, fecha
            ev = []
            self.tapk(ev, "M", 0)
            cx, cy = rec.user32.GetSystemMetrics(0) // 2, rec.user32.GetSystemMetrics(1) // 2
            x, y = cx + random.randint(-250, 250), cy + random.randint(-180, 180)
            t = random.uniform(0.9, 1.3)
            ev.append((t, lambda: rec.user32.SetCursorPos(x, y)))
            self.clicks(ev, t + random.uniform(0.2, 0.4), 1)
            self.tapk(ev, "M", t + random.uniform(0.8, 1.3))
            return ev

        return [("troca de arma andando (1-5)", 3, troca_armas),
                ("pra trás pulando + troca arma", 2, tras_pulando),
                ("marcando no mapa (M)", 1, marcar_mapa),
                ("andando em zigue-zague (W+D / W+A)", 4, frente_zigue),
                ("pra trás + lado + pulo (S+D+Espaço)", 2, tras_lado_pulo),
                ("girando e picaretando", 3, gira_picareta),
                ("andando, pulando e picaretando", 3, pula_picareta_andando),
                ("correndo até cansar (zig-zag)", 2, correr_cansar),
                ("olhando pra trás e voltando", 2, olha_tras_volta),
                ("lado + pulo + mirando", 2, lado_pulo_mira)]

    def match_over(self):
        """Fim de partida sem o painel rosa: voltou pro lobby sozinho, apareceu a tela
        de resumo/sair, ou o painel do time sumiu (sem barra verde) por muito tempo."""
        f = self.frame()
        for key in ("jogar", "sair", "confirmar"):
            if self.seen(key, f):
                self.log(f"[BR] Fim de partida detectado ('{key}' na tela)")
                return True
        if not self.saw_alive:
            return False
        line, _ = team_panel_state(self.vision.grab_rel(self.cfg.get("painel_time", PANEL_BOX)))
        if line:
            self._no_green_since = None
            return False
        if self._no_green_since is None:
            self._no_green_since = time.time()
        limite = float(self.cfg.get("sem_painel_segundos", 40))
        if time.time() - self._no_green_since >= limite:
            self.log(f"[BR] Painel do time sumiu há {limite:.0f}s = partida acabou")
            self._debug_shot("fim_partida")
            return True
        return False

    def _ground(self):
        self._no_green_since = None
        while True:
            if self.team_dead() or self.match_over():
                return
            combos = self._combos()
            w = [c[1] for c in combos]
            name, _, fn = random.choices(combos, w)[0]
            ev = fn()
            # as vezes emenda o proximo combo antes do atual terminar (sem parar nunca)
            if name != "marcando no mapa (M)" and random.random() < 0.45:
                name2, _, fn2 = random.choices(combos, w)[0]
                if name2 != "marcando no mapa (M)":
                    off = max(e[0] for e in ev) * random.uniform(0.55, 0.85)
                    ev += [(t + off, f) for t, f in fn2()]
                    name = f"{name} → {name2}"
            self.state = f"No chão: {name}"
            self.run_timeline(ev)
            self.wait(random.uniform(0.0, 0.15))

    def _quit(self):
        self._set("Time inteiro eliminado: saindo da partida")
        self._debug_shot("saindo")
        self._release()
        thr = float(self.cfg.get("limiar", 0.8))
        esc_tries = 0
        for _ in range(6):
            f = self.frame()
            if self.vision.find("jogar", f, thr):
                break
            if self.seen("onibus", f) or self.seen("onibus2", f):
                self._set("Ônibus na tela: cancelando saída")
                return
            if esc_tries >= 3:
                break
            s = self.vision.find("sair", f, thr)
            if s:
                self.click_at(s)
                self.wait(2)
                cf = self.seen("confirmar")
                if cf:
                    self.click_at(cf)
                self.wait(3)
                continue
            if self.vision.has("esc_sair"):
                esc_tries += 1
                self.tap("ESC")
                self.wait(1.2)
                e = self.seen("esc_sair")
                if not e:                                     # abre a aba das 3 barrinhas
                    m = self.seen("menu_tab")
                    if not m:
                        g = self.seen("menu_engrenagem")      # o ☰ fica logo a direita da engrenagem
                        if g:
                            m = (g[0] + int(self.cfg.get("menu_tab_dx", 97)), g[1])
                    if m:
                        self.click_at(m)
                        self.wait(1.0)
                        e = self.seen("esc_sair")
                if e:
                    self.click_at(e)
                    self.wait(1.5)
                    cf = self.seen("confirmar")
                    if cf:
                        self.click_at(cf)
                    self.wait(3)
                    continue
                self.tap("ESC")
            self.wait(2)
        self.last_quit = time.time()
        self._set("Voltando ao lobby")
        t = time.time()
        while time.time() - t < 90 and not self.seen("jogar"):
            if self.seen("onibus") or self.seen("onibus2"):
                return
            cf = self.seen("confirmar")
            if cf:
                self.click_at(cf)
            self.wait(2)
