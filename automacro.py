"""
Painel AutoMacro - Anti-AFK + auto-iniciar partidas (Fortnite)
Sem dependencias externas: usa tkinter + SendInput (scancodes) via ctypes.

Atalhos globais:
  F6  -> Iniciar / Parar macro
  F7  -> Capturar posicao do mouse para o ponto selecionado na lista
  F8  -> Parada de emergencia (para tudo)
  F9  -> Gravar / parar gravacao de rota
  F10 -> Reproduzir / parar rota selecionada
"""
import recorder as rec
import br_bot
import base64
import ctypes
import ctypes.wintypes as wt
import json
import os
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ----------------------------------------------------------------- Win32 input
user32 = ctypes.WinDLL("user32", use_last_error=True)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # coordenadas reais de tela
except Exception:
    pass

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_SCANCODE, KEYEVENTF_KEYUP = 0x0008, 0x0002
MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0001, 0x0002, 0x0004
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def _send(inp):
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# Scancodes (set 1) - jogos leem scancode, nao virtual-key
SCAN = {"W": 0x11, "A": 0x1E, "S": 0x1F, "D": 0x20, "SPACE": 0x39, "CTRL": 0x1D,
        "ESC": 0x01, "ENTER": 0x1C, "E": 0x12, "Q": 0x10, "SHIFT": 0x2A}


def key_down(name):
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(0, SCAN[name], KEYEVENTF_SCANCODE, 0, 0)
    _send(i)


def key_up(name):
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(0, SCAN[name], KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0)
    _send(i)


def tap(name, hold=0.08):
    key_down(name)
    time.sleep(hold)
    key_up(name)


def mouse_move_rel(dx, dy):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
    _send(i)


def click_at(x, y):
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.08)
    for flag in (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP):
        i = INPUT(type=INPUT_MOUSE)
        i.u.mi = MOUSEINPUT(0, 0, 0, flag, 0, 0)
        _send(i)
        time.sleep(0.06)


def cursor_pos():
    p = wt.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def foreground_title():
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


# ----------------------------------------------------------------- config
CFG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "automacro_config.json")
DEFAULT_CFG = {
    "only_when_focused": True,
    "window_filter": "Fortnite",
    "afk_min": 4.0, "afk_max": 9.0,          # intervalo entre acoes anti-AFK (s)
    "use_move": True, "use_jump": True, "use_crouch": False, "use_mouse": True,
    # --- bot Battle Royale
    "espera_onibus": 4,                       # s depois de detectar o onibus antes de comecar a mirar o pulo
    "pulo_segundos": 25,                      # sem icone do onibus: pula X s depois que o onibus aparece
    "pulo_max": 70,                           # limite de tempo no onibus
    "raio_alvo": 60,                          # px no mapa: pula quando o onibus estiver a menos disso do alvo
    "alvo_mapa": None,                        # [x, y] do ponto no mapa (tela com M aberto)
    "tempo_queda": 80,                        # sem modelo "no_ar": tempo planando ate chegar ao chao
    "giro_180": 1200,                         # px de mouse para virar 180 graus (depende da sensibilidade)
    "limiar": 0.8,                            # precisao do reconhecimento de imagem
    "espera_partida": 60,                     # s de espera no lobby depois de sair, antes de clicar JOGAR
    "use_route": False,                      # macro usa rota gravada no lugar do anti-AFK aleatorio
    "route_name": "",
    "route_reps": 1,
    "auto_start": True,
    "cycle_seconds": 60,                      # a cada X s roda a sequencia de cliques
    "points": [                               # pontos de clique da sequencia (lobby)
        {"name": "Botao JOGAR", "x": None, "y": None, "delay": 2.0},
        {"name": "Voltar ao lobby", "x": None, "y": None, "delay": 3.0},
        {"name": "Confirmar / Continuar", "x": None, "y": None, "delay": 2.0},
    ],
}


def load_cfg():
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CFG)
        cfg.update(data)
        return cfg
    except Exception:
        return json.loads(json.dumps(DEFAULT_CFG))


def save_cfg(cfg):
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------- macro engine
class Macro:
    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self.running = threading.Event()
        self.thread = None
        self.actions = 0
        self.cycles = 0
        self.started_at = None

    def start(self):
        if self.running.is_set():
            return
        self.running.set()
        self.started_at = time.time()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.log("Macro INICIADO")

    def stop(self):
        if not self.running.is_set():
            return
        self.running.clear()
        for k in ("W", "A", "S", "D", "SPACE", "CTRL"):
            key_up(k)
        self.log("Macro PARADO")

    def _wait(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if not self.running.is_set():
                return False
            time.sleep(0.05)
        return True

    def _focused(self):
        if not self.cfg["only_when_focused"]:
            return True
        return self.cfg["window_filter"].lower() in foreground_title().lower()

    def _anti_afk_action(self):
        c = self.cfg
        options = []
        if c["use_move"]:
            options += ["move"] * 3
        if c["use_jump"]:
            options.append("jump")
        if c["use_crouch"]:
            options.append("crouch")
        if c["use_mouse"]:
            options.append("mouse")
        if not options:
            return
        act = random.choice(options)
        if act == "move":
            k = random.choice(["W", "A", "S", "D"])
            tap(k, random.uniform(0.15, 0.6))
            desc = f"andar {k}"
        elif act == "jump":
            tap("SPACE")
            desc = "pular"
        elif act == "crouch":
            tap("CTRL", random.uniform(0.1, 0.3))
            desc = "agachar"
        else:
            dx = random.randint(-120, 120)
            for _ in range(10):
                mouse_move_rel(dx // 10, random.randint(-3, 3))
                time.sleep(0.01)
            desc = "mexer camera"
        self.actions += 1
        self.log(f"Anti-AFK: {desc}")

    def _run_sequence(self):
        pts = [p for p in self.cfg["points"] if p.get("x") is not None]
        if not pts:
            return
        self.cycles += 1
        self.log(f"Sequencia de inicio #{self.cycles}")
        saved = cursor_pos()
        for p in pts:
            if not self.running.is_set() or not self._focused():
                break
            click_at(p["x"], p["y"])
            self.log(f"  clique: {p['name']} ({p['x']},{p['y']})")
            if not self._wait(float(p.get("delay", 2))):
                break
        user32.SetCursorPos(*saved)

    def _loop(self):
        last_seq = 0.0
        warned = False
        while self.running.is_set():
            if not self._focused():
                if not warned:
                    self.log(f"Aguardando janela '{self.cfg['window_filter']}' em foco...")
                    warned = True
                self._wait(1)
                continue
            warned = False
            if self.cfg["auto_start"] and time.time() - last_seq >= float(self.cfg["cycle_seconds"]):
                self._run_sequence()
                last_seq = time.time()
            if self.cfg.get("use_route") and self.cfg.get("route_name"):
                events = rec.load_route(self.cfg["route_name"])
                if events:
                    self.log(f"Rota: '{self.cfg['route_name']}'")
                    if rec.play(events, self.running.is_set, self._focused):
                        self.actions += 1
                    self._wait(1)
                    continue
            self._anti_afk_action()
            lo, hi = float(self.cfg["afk_min"]), float(self.cfg["afk_max"])
            self._wait(random.uniform(min(lo, hi), max(lo, hi)))


# ----------------------------------------------------------------- hotkeys
WM_HOTKEY = 0x0312
VK_F6, VK_F7, VK_F8, VK_F9, VK_F10, VK_F11 = 0x75, 0x76, 0x77, 0x78, 0x79, 0x7A


def hotkey_thread(callback):
    def run():
        for hid, vk in ((1, VK_F6), (2, VK_F7), (3, VK_F8), (4, VK_F9), (5, VK_F10), (6, VK_F11)):
            if not user32.RegisterHotKey(None, hid, 0, vk):
                callback(-hid)
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                callback(msg.wParam)
    threading.Thread(target=run, daemon=True).start()


# ----------------------------------------------------------------- UI
BG, PANEL, FG, ACC, MUTED, RED, GREEN = "#12131a", "#1c1e28", "#e8e8ef", "#7c5cff", "#8a8ca0", "#ff5c6c", "#3ddc97"


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_cfg()
        self.macro = Macro(self.cfg, self.log)
        self.rec = rec.Recorder(ignore_vks=range(VK_F6, VK_F11 + 1))
        self.bot = br_bot.BRBot(self.cfg, self.log, self.macro._focused)
        self.playing = threading.Event()
        self.spins = {}
        self.v = {}
        root.title("Pé de Feijão Coreano")
        root.configure(bg=BG)
        root.geometry("420x560")
        root.minsize(380, 480)
        root.attributes("-topmost", True)

        st = ttk.Style()
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=PANEL)
        st.configure("TLabelframe", background=BG, bordercolor="#2c2f3d")
        st.configure("TLabelframe.Label", background=BG, foreground=ACC, font=("Segoe UI", 10, "bold"))
        st.configure("TCheckbutton", background=BG, foreground=FG)
        st.map("TCheckbutton", background=[("active", BG)])
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG, rowheight=24)
        st.configure("Treeview.Heading", background="#262938", foreground=FG)
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=PANEL, foreground=FG, padding=(14, 6), font=("Segoe UI", 10, "bold"))
        st.map("TNotebook.Tab", background=[("selected", ACC)], foreground=[("selected", "white")])

        # ---------------- tela principal (simples)
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text="Pé de Feijão Coreano", bg=BG, fg=FG, font=("Segoe UI", 16, "bold")).pack(side="left")
        self.status = tk.Label(head, text="● PARADO", bg=BG, fg=RED, font=("Segoe UI", 11, "bold"))
        self.status.pack(side="right")

        self.btn = tk.Button(root, text="▶  INICIAR  (F6)", command=self.toggle, bg=ACC, fg="white",
                             activebackground="#6a4be0", relief="flat", font=("Segoe UI", 14, "bold"), height=2)
        self.btn.pack(fill="x", padx=16, pady=8)

        self.simple_state = tk.Label(root, text="", bg=BG, fg=FG, font=("Segoe UI", 10))
        self.simple_state.pack(anchor="w", padx=16)

        card = tk.Frame(root, bg=PANEL)
        card.pack(fill="x", padx=16, pady=10)
        tk.Label(card, text="Preparação (só uma vez)", bg=PANEL, fg=ACC,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        tk.Label(card, text="No jogo aperte F11 na tela certa, depois clique em Recortar.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=12, pady=(0, 6))
        self.simple_rows = {}
        for key, label in (("jogar", "Botão JOGAR"), ("onibus", "Ônibus (Espaço para pular)"),
                           ("menu_tab", "ESC → ícone ☰ (3 barrinhas)"), ("esc_sair", "ESC → Voltar ao Lobby")):
            r = tk.Frame(card, bg=PANEL); r.pack(fill="x", padx=12, pady=3)
            ic = tk.Label(r, text="", bg=PANEL, font=("Segoe UI", 11, "bold"), width=2)
            ic.pack(side="left")
            tk.Label(r, text=label, bg=PANEL, fg=FG, font=("Segoe UI", 10)).pack(side="left", padx=4)
            tk.Button(r, text="Recortar", command=lambda k=key: self.crop_model(k), bg="#2c2f3d", fg=FG,
                      relief="flat", activebackground=ACC, padx=10).pack(side="right")
            self.simple_rows[key] = ic
        tk.Frame(card, bg=PANEL, height=8).pack()

        er = tk.Frame(root, bg=BG); er.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(er, text="Esperar entre partidas (s):", bg=BG, fg=FG, font=("Segoe UI", 10)).pack(side="left")
        self._spin(er, "espera_partida", 0, 1800, cast=int, inc=10)

        foot = tk.Frame(root, bg=BG); foot.pack(fill="x", padx=16, pady=(0, 6))
        tk.Button(foot, text="⚙  Ajustes", command=self.show_tools, bg=PANEL, fg=FG, relief="flat",
                  activebackground="#2c2f3d", padx=12, pady=4).pack(side="left")
        tk.Label(foot, text="F8 = parar tudo", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

        # ---------------- janela de ajustes (escondida)
        self.tools = tk.Toplevel(root, bg=BG)
        self.tools.title("Ajustes")
        self.tools.geometry("600x860")
        self.tools.attributes("-topmost", True)
        self.tools.protocol("WM_DELETE_WINDOW", self.tools.withdraw)
        self.tools.withdraw()

        self.stats = tk.Label(self.tools, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.stats.pack(anchor="w", padx=14, pady=(8, 0))

        self.nb = ttk.Notebook(self.tools)
        self.nb.pack(fill="x", padx=14, pady=6)
        tab_br, tab_macro, tab_rotas = (tk.Frame(self.nb, bg=BG) for _ in range(3))
        self.nb.add(tab_br, text="Bot (avançado)")
        self.nb.add(tab_macro, text="Macro / Anti-AFK")
        self.nb.add(tab_rotas, text="Rotas")
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self.update_status())
        self._build_br(tab_br)

        # Anti-AFK
        f1 = ttk.LabelFrame(tab_macro, text=" Anti-AFK ")
        f1.pack(fill="x", padx=6, pady=6)
        row = tk.Frame(f1, bg=BG); row.pack(fill="x", padx=8, pady=4)
        for key, label in (("use_move", "Andar (WASD)"), ("use_jump", "Pular"),
                           ("use_crouch", "Agachar"), ("use_mouse", "Mexer câmera")):
            self.v[key] = tk.BooleanVar(value=self.cfg[key])
            ttk.Checkbutton(row, text=label, variable=self.v[key], command=self.sync).pack(side="left", padx=4)
        row2 = tk.Frame(f1, bg=BG); row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="Intervalo (s):").pack(side="left")
        self._spin(row2, "afk_min", 1, 120)
        ttk.Label(row2, text="até").pack(side="left", padx=4)
        self._spin(row2, "afk_max", 1, 120)

        # Auto start
        f2 = ttk.LabelFrame(tab_macro, text=" Auto-iniciar partidas (cliques em sequência) ")
        f2.pack(fill="both", expand=False, padx=6, pady=6)
        r3 = tk.Frame(f2, bg=BG); r3.pack(fill="x", padx=8, pady=4)
        self.v["auto_start"] = tk.BooleanVar(value=self.cfg["auto_start"])
        ttk.Checkbutton(r3, text="Ativado", variable=self.v["auto_start"], command=self.sync).pack(side="left")
        ttk.Label(r3, text="   Rodar sequência a cada (s):").pack(side="left")
        self._spin(r3, "cycle_seconds", 10, 3600)

        self.tree = ttk.Treeview(f2, columns=("name", "pos", "delay"), show="headings", height=4)
        for c, t, w in (("name", "Ponto", 200), ("pos", "Posição", 110), ("delay", "Espera (s)", 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="x", padx=8, pady=4)
        br = tk.Frame(f2, bg=BG); br.pack(fill="x", padx=8, pady=(0, 6))
        for txt, cmd in (("Capturar (F7)", self.capture_selected), ("+ Ponto", self.add_point),
                         ("Remover", self.remove_point), ("Espera...", self.edit_delay), ("Testar", self.test_seq)):
            tk.Button(br, text=txt, command=cmd, bg=PANEL, fg=FG, relief="flat",
                      activebackground="#2c2f3d", padx=8).pack(side="left", padx=2)
        tk.Label(f2, text="Selecione um ponto, deixe o mouse sobre o botão no jogo e aperte F7.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 6))
        self.refresh_tree()

        # Gravador de rota
        f4 = ttk.LabelFrame(tab_rotas, text=" Gravador de rota ")
        f4.pack(fill="x", padx=6, pady=6)
        r5 = tk.Frame(f4, bg=BG); r5.pack(fill="x", padx=8, pady=4)
        ttk.Label(r5, text="Nome:").pack(side="left")
        self.route_entry = tk.Entry(r5, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", width=18)
        self.route_entry.insert(0, "rota1")
        self.route_entry.pack(side="left", padx=6)
        self.rec_btn = tk.Button(r5, text="● Gravar (F9)", command=self.toggle_record, bg=PANEL, fg=RED,
                                 relief="flat", activebackground="#2c2f3d", padx=8)
        self.rec_btn.pack(side="left", padx=2)
        self.rec_status = tk.Label(r5, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold"))
        self.rec_status.pack(side="left", padx=6)

        self.route_list = tk.Listbox(f4, bg=PANEL, fg=FG, selectbackground=ACC, relief="flat",
                                     height=4, exportselection=False, font=("Segoe UI", 9))
        self.route_list.pack(fill="x", padx=8, pady=4)
        self.route_list.bind("<<ListboxSelect>>", self.on_route_select)

        r6 = tk.Frame(f4, bg=BG); r6.pack(fill="x", padx=8, pady=(0, 4))
        self.play_btn = tk.Button(r6, text="▶ Reproduzir (F10)", command=self.toggle_play, bg=PANEL, fg=GREEN,
                                  relief="flat", activebackground="#2c2f3d", padx=8)
        self.play_btn.pack(side="left", padx=2)
        tk.Button(r6, text="Excluir", command=self.delete_route, bg=PANEL, fg=FG, relief="flat",
                  activebackground="#2c2f3d", padx=8).pack(side="left", padx=2)
        ttk.Label(r6, text="  Repetições (0 = infinito):").pack(side="left")
        self._spin(r6, "route_reps", 0, 9999, cast=int)

        self.v["use_route"] = tk.BooleanVar(value=self.cfg.get("use_route", False))
        ttk.Checkbutton(f4, text="No macro (F6): usar a rota selecionada no lugar do anti-AFK aleatório",
                        variable=self.v["use_route"], command=self.sync).pack(anchor="w", padx=8)
        tk.Label(f4, text="Aperte F9 no jogo, faça a rota, aperte F9 de novo. Comece sempre do mesmo lugar/ângulo.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 6))
        self.refresh_routes()

        # Seguranca
        f3 = ttk.LabelFrame(self.tools, text=" Segurança ")
        f3.pack(fill="x", padx=14, pady=6)
        r4 = tk.Frame(f3, bg=BG); r4.pack(fill="x", padx=8, pady=6)
        self.v["only_when_focused"] = tk.BooleanVar(value=self.cfg["only_when_focused"])
        ttk.Checkbutton(r4, text="Só agir com a janela em foco:", variable=self.v["only_when_focused"],
                        command=self.sync).pack(side="left")
        self.win = tk.Entry(r4, bg=PANEL, fg=FG, insertbackground=FG, relief="flat", width=16)
        self.win.insert(0, self.cfg["window_filter"])
        self.win.pack(side="left", padx=6)
        self.win.bind("<KeyRelease>", lambda e: self.sync())

        # Log
        self.logbox = tk.Text(root, bg="#0c0d12", fg=MUTED, relief="flat", height=5, font=("Consolas", 9), wrap="word")
        self.logbox.pack(fill="both", expand=True, padx=16, pady=(4, 14))

        hotkey_thread(lambda h: root.after(0, self.on_hotkey, h))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("Pronto. F6 inicia/para · F11 tira print · F8 para tudo")
        self.update_status()
        self.tick()

    def _spin(self, parent, key, lo, hi, cast=float, inc=1):
        s = tk.Spinbox(parent, from_=lo, to=hi, increment=inc, width=6, bg=PANEL, fg=FG,
                       buttonbackground=PANEL, relief="flat", command=self.sync)
        s.delete(0, "end"); s.insert(0, self.cfg.get(key, DEFAULT_CFG.get(key)))
        s.bind("<KeyRelease>", lambda e: self.sync())
        s.pack(side="left", padx=4)
        self.spins[key] = (s, cast, lo, hi)
        return s

    def sync(self):
        for k, var in self.v.items():
            self.cfg[k] = var.get()
        for key, (w, cast, lo, hi) in self.spins.items():
            try:
                self.cfg[key] = min(hi, max(lo, cast(float(w.get()))))
            except ValueError:
                pass
        self.cfg["window_filter"] = self.win.get().strip() or "Fortnite"
        save_cfg(self.cfg)

    # ------------------------------------------------------------- aba Battle Royale
    def _build_br(self, p):
        self.br_state = tk.Label(p, text="Estado: Parado", bg=BG, fg=FG, font=("Segoe UI", 10, "bold"))
        self.br_state.pack(anchor="w", padx=8, pady=(8, 2))

        fm = ttk.LabelFrame(p, text=" 1. Modelos (recortes de print do jogo) ")
        fm.pack(fill="x", padx=6, pady=6)
        self.models = ttk.Treeview(fm, columns=("nome", "status"), show="headings", height=8)
        self.models.heading("nome", text="O que o bot precisa reconhecer")
        self.models.heading("status", text="Status")
        self.models.column("nome", width=330, anchor="w")
        self.models.column("status", width=110, anchor="w")
        self.models.pack(fill="x", padx=8, pady=4)
        self.models.bind("<<TreeviewSelect>>", lambda e: self._model_hint())
        self.model_hint = tk.Label(fm, text="", bg=BG, fg=ACC, font=("Segoe UI", 9), wraplength=520, justify="left")
        self.model_hint.pack(anchor="w", padx=8)
        bm = tk.Frame(fm, bg=BG); bm.pack(fill="x", padx=8, pady=4)
        for txt, cmd in (("Tirar print (F11)", self.take_print), ("Recortar modelo...", self.crop_model),
                         ("Testar detecção", self.test_detect), ("Abrir pasta", self.open_models)):
            tk.Button(bm, text=txt, command=cmd, bg=PANEL, fg=FG, relief="flat",
                      activebackground="#2c2f3d", padx=8).pack(side="left", padx=2)
        tk.Label(fm, text="No jogo aperte F11 na tela certa → selecione a linha → Recortar → arraste um retângulo "
                          "em volta da parte que só aparece naquela tela.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=520, justify="left").pack(anchor="w", padx=8, pady=(0, 6))
        self.refresh_models()

        fj = ttk.LabelFrame(p, text=" 2. Pulo do ônibus ")
        fj.pack(fill="x", padx=6, pady=6)
        r = tk.Frame(fj, bg=BG); r.pack(fill="x", padx=8, pady=4)
        tk.Button(r, text="Marcar alvo no mapa...", command=self.mark_target, bg=PANEL, fg=FG, relief="flat",
                  activebackground="#2c2f3d", padx=8).pack(side="left")
        self.alvo_lbl = tk.Label(r, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.alvo_lbl.pack(side="left", padx=8)
        r = tk.Frame(fj, bg=BG); r.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(r, text="Raio do alvo (px):").pack(side="left")
        self._spin(r, "raio_alvo", 10, 500)
        ttk.Label(r, text="  Sem ícone: pular após (s):").pack(side="left")
        self._spin(r, "pulo_segundos", 3, 120)
        self._alvo_text()

        fc = ttk.LabelFrame(p, text=" 3. Ajustes ")
        fc.pack(fill="x", padx=6, pady=6)
        r = tk.Frame(fc, bg=BG); r.pack(fill="x", padx=8, pady=4)
        ttk.Label(r, text="Giro de 180° (px do mouse):").pack(side="left")
        self._spin(r, "giro_180", 100, 20000, cast=int, inc=50)
        tk.Button(r, text="Testar giro", command=self.test_turn, bg=PANEL, fg=FG, relief="flat",
                  activebackground="#2c2f3d", padx=8).pack(side="left", padx=6)
        r = tk.Frame(fc, bg=BG); r.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(r, text="Precisão imagem:").pack(side="left")
        self._spin(r, "limiar", 0.5, 0.99, inc=0.01)
        ttk.Label(r, text="  Sem modelo 'no ar': queda (s):").pack(side="left")
        self._spin(r, "tempo_queda", 10, 240)

    def refresh_models(self):
        sel = self.models.selection()
        self.models.delete(*self.models.get_children())
        for key, name, _, req in br_bot.SLOTS:
            ok = self.bot.vision.has(key)
            st = "✓ pronto" if ok else ("✗ FALTA" if req else "— opcional")
            self.models.insert("", "end", iid=key, values=(name, st))
        self.models.selection_set(sel[0] if sel else br_bot.SLOTS[0][0])
        self._model_hint()
        for key, ic in self.simple_rows.items():
            ok = self.bot.vision.has(key) or (key == "menu_tab" and self.bot.vision.has("menu_engrenagem"))
            ic.config(text="✓" if ok else "✗", fg=GREEN if ok else RED)

    def _model_hint(self):
        s = self.models.selection()
        if s:
            hint = next(h for k, _, h, _ in br_bot.SLOTS if k == s[0])
            self.model_hint.config(text="→ Recorte: " + hint)

    def _alvo_text(self):
        a = self.cfg.get("alvo_mapa")
        self.alvo_lbl.config(text=f"Alvo: {a[0]}, {a[1]}" if a else "sem alvo (vai usar o tempo)")

    def take_print(self):
        img, _, _ = self.bot.vision.grab_bgr()
        os.makedirs(br_bot.PRINTS_DIR, exist_ok=True)
        path = os.path.join(br_bot.PRINTS_DIR, time.strftime("print_%Y%m%d_%H%M%S.png"))
        br_bot.imwrite(path, img)
        self.log(f"Print salvo: {os.path.basename(path)}")

    def _pick_print(self, title):
        os.makedirs(br_bot.PRINTS_DIR, exist_ok=True)
        return filedialog.askopenfilename(parent=self.root, title=title, initialdir=br_bot.PRINTS_DIR,
                                          filetypes=[("Imagens", "*.png")])

    def _image_window(self, path, mode, title, on_done):
        img = br_bot.imread(path)
        if img is None:
            return
        cv2 = br_bot.cv2
        h, w = img.shape[:2]
        sc = min(1.0, 1280 / w, 740 / h)
        disp = cv2.resize(img, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA)
        photo = tk.PhotoImage(data=base64.b64encode(cv2.imencode(".png", disp)[1].tobytes()))
        win = tk.Toplevel(self.root, bg=BG)
        win.title(title); win.attributes("-topmost", True)
        tk.Label(win, text=title, bg=BG, fg=FG, font=("Segoe UI", 10, "bold")).pack(pady=4)
        cv = tk.Canvas(win, width=disp.shape[1], height=disp.shape[0], highlightthickness=0, cursor="crosshair")
        cv.pack(padx=6, pady=6)
        cv.create_image(0, 0, anchor="nw", image=photo)
        cv.image = photo
        st = {}
        if mode == "point":
            def click(e):
                on_done((int(e.x / sc), int(e.y / sc))); win.destroy()
            cv.bind("<Button-1>", click)
            return

        def press(e):
            st["p"] = (e.x, e.y)
            st["r"] = cv.create_rectangle(e.x, e.y, e.x, e.y, outline="#ff3b6b", width=2)

        def drag(e):
            if "r" in st:
                cv.coords(st["r"], *st["p"], e.x, e.y)

        def release(e):
            if "p" not in st:
                return
            x0, x1 = sorted((st["p"][0], e.x)); y0, y1 = sorted((st["p"][1], e.y))
            X0, Y0, X1, Y1 = (int(v / sc) for v in (x0, y0, x1, y1))
            if X1 - X0 < 10 or Y1 - Y0 < 10:
                return
            on_done(img[Y0:Y1, X0:X1].copy()); win.destroy()
        cv.bind("<ButtonPress-1>", press); cv.bind("<B1-Motion>", drag); cv.bind("<ButtonRelease-1>", release)

    def crop_model(self, key=None):
        if key is None:
            s = self.models.selection()
            if not s:
                return
            key = s[0]
        name = next(n for k, n, _, _ in br_bot.SLOTS if k == key)
        path = self._pick_print(f"Escolha o print para: {name}")
        if not path:
            return

        def done(crop):
            os.makedirs(br_bot.MODELS_DIR, exist_ok=True)
            br_bot.imwrite(br_bot.Vision.path(key), crop)
            self.log(f"Modelo '{name}' salvo ({crop.shape[1]}x{crop.shape[0]})")
            self.refresh_models()
        self._image_window(path, "rect", f"Arraste um retângulo: {name}", done)

    def mark_target(self):
        path = self._pick_print("Escolha um print com o MAPA aberto (M)")
        if not path:
            return

        def done(pt):
            self.cfg["alvo_mapa"] = list(pt); save_cfg(self.cfg); self._alvo_text()
            self.log(f"Alvo do pulo marcado em {pt}")
        self._image_window(path, "point", "Clique no ponto do mapa onde quer cair", done)

    def test_detect(self):
        self.log("Testando detecção em 3 s... deixe o jogo na tela.")

        def go():
            time.sleep(3)
            v = self.bot.vision
            f = v.frame()
            thr = float(self.cfg.get("limiar", 0.8))
            for key, name, _, _ in br_bot.SLOTS:
                r = v.score(key, f)
                if r:
                    self.log(f"  {name}: {r[2]:.2f} {'✓ VISTO' if r[2] >= thr else '✗'}")
        threading.Thread(target=go, daemon=True).start()

    def test_turn(self):
        self.sync()
        self.log("Em 3 s vou virar 180° (deixe o jogo em foco). Ajuste até virar certinho.")

        def go():
            time.sleep(3)
            px = int(self.cfg["giro_180"]); steps = 30
            for _ in range(steps):
                rec._mouse(rec.MOVE, px // steps, 0); time.sleep(0.01)
        threading.Thread(target=go, daemon=True).start()

    def open_models(self):
        os.makedirs(br_bot.MODELS_DIR, exist_ok=True)
        os.startfile(br_bot.MODELS_DIR)

    def current_tab(self):
        if self.tools.state() == "withdrawn":
            return "br"
        return ("br", "macro", "rotas")[self.nb.index(self.nb.select())]

    def show_tools(self):
        self.tools.deiconify(); self.tools.lift()

    def log(self, msg):
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.txt"), "a", encoding="utf-8") as fh:
                fh.write(time.strftime("[%d/%m %H:%M:%S] ") + msg + "\n")
        except OSError:
            pass

        def put():
            self.logbox.insert("end", time.strftime("[%H:%M:%S] ") + msg + "\n")
            lines = int(self.logbox.index("end-1c").split(".")[0])
            if lines > 300:
                self.logbox.delete("1.0", f"{lines - 300}.0")
            self.logbox.see("end")
        self.root.after(0, put)

    # pontos
    def refresh_tree(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.cfg["points"]):
            pos = f"{p['x']}, {p['y']}" if p.get("x") is not None else "— não definido —"
            self.tree.insert("", "end", iid=str(i), values=(p["name"], pos, p.get("delay", 2)))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        elif self.cfg["points"]:
            self.tree.selection_set("0")

    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def capture_selected(self):
        i = self._sel()
        if i is None:
            return
        x, y = cursor_pos()
        self.cfg["points"][i].update(x=x, y=y)
        save_cfg(self.cfg); self.refresh_tree()
        self.log(f"Capturado '{self.cfg['points'][i]['name']}' em ({x},{y})")

    def add_point(self):
        name = self._ask("Nome do ponto:", f"Ponto {len(self.cfg['points']) + 1}")
        if name:
            self.cfg["points"].append({"name": name, "x": None, "y": None, "delay": 2.0})
            save_cfg(self.cfg); self.refresh_tree()
            self.tree.selection_set(str(len(self.cfg["points"]) - 1))

    def remove_point(self):
        i = self._sel()
        if i is not None:
            self.cfg["points"].pop(i)
            save_cfg(self.cfg); self.refresh_tree()

    def edit_delay(self):
        i = self._sel()
        if i is None:
            return
        val = self._ask("Espera após o clique (s):", str(self.cfg["points"][i].get("delay", 2)))
        try:
            self.cfg["points"][i]["delay"] = max(0.1, float(val))
            save_cfg(self.cfg); self.refresh_tree()
        except (TypeError, ValueError):
            pass

    def test_seq(self):
        self.log("Teste: a sequência roda em 3 s (troque para o jogo)...")
        def go():
            time.sleep(3)
            self.macro.running.set()
            self.macro._run_sequence()
            if not self.macro.thread or not self.macro.thread.is_alive():
                self.macro.running.clear()
        threading.Thread(target=go, daemon=True).start()

    # rotas
    def refresh_routes(self):
        self.routes = rec.list_routes()
        self.route_list.delete(0, "end")
        for name, dur, n in self.routes:
            self.route_list.insert("end", f"{name}   ·   {dur:.1f}s   ·   {n} eventos")
        names = [r[0] for r in self.routes]
        if self.cfg.get("route_name") in names:
            i = names.index(self.cfg["route_name"])
            self.route_list.selection_set(i); self.route_list.see(i)

    def on_route_select(self, _=None):
        s = self.route_list.curselection()
        if s:
            self.cfg["route_name"] = self.routes[s[0]][0]
            save_cfg(self.cfg)

    def toggle_record(self):
        if self.rec.recording:
            events = self.rec.stop()
            self.rec_btn.config(text="● Gravar (F9)")
            if not events:
                self.log("Gravação vazia, nada salvo.")
                return
            name = rec.save_route(self.route_entry.get() or time.strftime("rota_%H%M%S"), events)
            self.cfg["route_name"] = name
            save_cfg(self.cfg); self.refresh_routes()
            self.log(f"Rota '{name}' salva ({events[-1][1]:.1f}s, {len(events)} eventos)")
            return
        if self.macro.running.is_set() or self.playing.is_set():
            self.log("Pare o macro/reprodução antes de gravar.")
            return
        self.rec.start()
        if self.rec.error:
            self.log(f"Erro ao iniciar gravação (código {self.rec.error})")
            self.rec.stop()
            return
        self.rec_btn.config(text="■ Parar (F9)")
        self.log("GRAVANDO... faça a rota no jogo e aperte F9 para parar.")

    def toggle_play(self):
        if self.playing.is_set():
            self.playing.clear(); self.log("Reprodução parada.")
            return
        if self.rec.recording:
            return
        name = self.cfg.get("route_name")
        events = rec.load_route(name) if name else []
        if not events:
            self.log("Selecione uma rota gravada primeiro.")
            return
        self.sync()
        reps = int(self.cfg.get("route_reps", 1))
        self.playing.set()
        self.log(f"Reproduzindo '{name}' ({'∞' if reps == 0 else reps}x). Ela espera o jogo estar em foco.")

        def go():
            time.sleep(0.5)
            i = 0
            while self.playing.is_set() and (reps == 0 or i < reps):
                if not rec.play(events, self.playing.is_set, self.macro._focused):
                    break
                i += 1
                self.log(f"  rota concluída ({i})")
                end = time.time() + 1
                while self.playing.is_set() and time.time() < end:
                    time.sleep(0.05)
            self.playing.clear()
            self.log("Reprodução finalizada.")
        threading.Thread(target=go, daemon=True).start()

    def delete_route(self):
        s = self.route_list.curselection()
        if not s:
            return
        name = self.routes[s[0]][0]
        if messagebox.askyesno("Excluir", f"Excluir a rota '{name}'?", parent=self.root):
            rec.delete_route(name)
            self.refresh_routes(); self.log(f"Rota '{name}' excluída")

    def _ask(self, prompt, default=""):
        win = tk.Toplevel(self.root, bg=BG); win.title(""); win.attributes("-topmost", True)
        tk.Label(win, text=prompt, bg=BG, fg=FG).pack(padx=12, pady=(12, 4))
        e = tk.Entry(win, bg=PANEL, fg=FG, insertbackground=FG, width=30); e.insert(0, default); e.pack(padx=12)
        e.focus_set(); e.select_range(0, "end")
        out = {}
        def ok(_=None):
            out["v"] = e.get().strip(); win.destroy()
        e.bind("<Return>", ok)
        tk.Button(win, text="OK", command=ok, bg=ACC, fg="white", relief="flat", width=10).pack(pady=10)
        win.grab_set(); self.root.wait_window(win)
        return out.get("v")

    # controle
    def toggle(self):
        """F6: se algo estiver rodando, para. Senao inicia o modo da aba aberta."""
        self.sync()
        if self.bot.running.is_set() or self.macro.running.is_set() or self.playing.is_set():
            self.bot.stop(); self.macro.stop(); self.playing.clear()
        else:
            tab = self.current_tab()
            if tab == "br":
                self.bot.start()
                if self.bot.running.is_set():       # minimiza o painel pra nao cobrir o jogo
                    self.tools.withdraw()
                    self.root.iconify()
            elif tab == "macro":
                self.macro.start()
            else:
                self.toggle_play()
        self.update_status()

    def update_status(self):
        if self.bot.running.is_set():
            txt, on = "● BOT BR RODANDO", True
        elif self.macro.running.is_set():
            txt, on = "● MACRO RODANDO", True
        elif self.playing.is_set():
            txt, on = "● ROTA RODANDO", True
        else:
            txt, on = "● PARADO", False
        self.status.config(text=txt, fg=GREEN if on else RED)
        label = {"br": "▶  INICIAR  (F6)", "macro": "▶  INICIAR MACRO  (F6)",
                 "rotas": "▶  REPRODUZIR ROTA  (F6)"}[self.current_tab()]
        self.btn.config(text="■  PARAR  (F6)" if on else label, bg=RED if on else ACC)

    def on_hotkey(self, h):
        if h == 1:
            self.toggle()
        elif h == 2:
            self.capture_selected()
        elif h == 3:
            self.macro.stop(); self.bot.stop(); self.playing.clear()
            if self.rec.recording:
                self.toggle_record()
            self.update_status(); self.log("PARADA DE EMERGÊNCIA (F8)")
        elif h == 4:
            self.toggle_record()
        elif h == 5:
            self.toggle_play()
        elif h == 6:
            self.take_print()
        elif h < 0:
            self.log(f"Aviso: não foi possível registrar o atalho F{5 - h} (em uso por outro app)")

    def tick(self):
        m = self.macro
        up = int(time.time() - m.started_at) if (m.started_at and m.running.is_set()) else 0
        self.stats.config(text=f"Tempo: {up // 3600:02d}:{up % 3600 // 60:02d}:{up % 60:02d}   ·   "
                               f"Ações anti-AFK: {m.actions}   ·   Sequências: {m.cycles}")
        self.update_status()
        self.br_state.config(text=f"Estado: {self.bot.state}   ·   Partidas: {self.bot.matches}")
        self.simple_state.config(text=f"{self.bot.state}   ·   {self.bot.matches} partidas")
        if self.rec.recording:
            self.rec_status.config(text=f"● GRAVANDO {self.rec.elapsed():.0f}s · {len(self.rec.events)} ev", fg=RED)
        elif self.playing.is_set():
            self.rec_status.config(text="▶ REPRODUZINDO", fg=GREEN)
        else:
            self.rec_status.config(text="")
        self.play_btn.config(text="■ Parar (F10)" if self.playing.is_set() else "▶ Reproduzir (F10)")
        self.root.after(500, self.tick)

    def on_close(self):
        self.macro.stop(); self.bot.stop(); self.playing.clear()
        if self.rec.recording:
            self.rec.stop()
        self.sync(); self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
