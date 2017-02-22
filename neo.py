import contextlib
import threading

from .lib import neovim
from .lib import util

NEOVIM_PATH = util.which('nvim')
if not NEOVIM_PATH:
    raise Exception('cannot find nvim executable')

INSERT_MODES = ['i']
VISUAL_MODES = ['V', 'v', '\x16']


class Screen:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.resize(1, 1)

    def resize(self, w, h):
        self.w = w
        self.h = h
        self.screen = [[''] * w for i in range(h)]

    def clear(self):
        self.resize(self.w, self.h)

    def redraw(self, updates):
        blacklist = [
            'mode_change',
            'bell', 'mouse_on', 'highlight_set',
            'update_fb', 'update_bg', 'update_sp', 'clear',
            'scroll', 'set_scroll_region',
        ]
        for cmd in updates:
            name, args = cmd[0], cmd[1:]
            if name == 'cursor_goto':
                self.y, self.x = args[0]
            elif name == 'eol_clear':
                self.x = 0
                self.y += 1
            elif name == 'put':
                for cs in args:
                    for c in cs:
                        self[self.x, self.y] = c
                        self.x += 1
            elif name == 'resize':
                self.resize(*args[0])
            elif name in blacklist:
                pass
            # else:
            #     print('unknown update cmd', name)

    def __setitem__(self, xy, c):
        x, y = xy
        try:
            self.screen[y][x] = c
        except IndexError:
            pass

    def __getitem__(self, y):
        return ''.join(self.screen[y])

    def __str__(self):
        return '\n'.join([self[y] for y in range(self.h)])


class Vim:
    def __init__(self, nv=None):
        self.nv = nv
        if nv is None:
            self.notif_cb = None
            self.screen = Screen()

    def _setup(self):
        self.nv = neovim.attach('child', argv=[NEOVIM_PATH, '--embed'])
        self._sem = threading.Semaphore(0)
        self._thread = t = threading.Thread(target=self._event_loop)
        t.daemon = True
        t.start()

        self._sem.acquire()
        self.cmd('set noswapfile')
        self.cmd('set hidden')
        self.nv.ui_attach(80, 24, True)

    def _event_loop(self):
        def on_notification(method, updates):
            if method == 'redraw':
                vim.screen.redraw(updates)
            if vim.notif_cb:
                vim.notif_cb(method, updates)

        def on_request(method, args):
            raise NotImplemented

        def on_setup():
            self._sem.release()

        self.nv.run_loop(on_request, on_notification, on_setup)

    def cmd(self, *args, **kwargs):
        return self.nv.command_output(*args, **kwargs)

    def eval(self, *cmds):
        if len(cmds) == 1:
            return self.nv.eval(cmds[0])
        else:
            return [self.nv.eval(c) for c in cmds]

    # buffer methods
    def buf_activate(self, buf):
        self.cmd('b! {:d}'.format(buf.number))

    def buf_new(self):
        self.cmd('enew')
        return max((b.number, b) for b in self.nv.buffers)[1]

    def buf_close(self, buf):
        self.cmd('bw! {:d}'.format(buf.number))

    def press(self, key):
        self.nv.feedkeys(self.nv.replace_termcodes(key))

    @property
    def sel(self):
        r1, c1, r2, c2 = self.eval('line(".")', 'col(".")', 'line("v")', 'col("v")')
        return (r2 - 1, c2 - 1), (r1 - 1, c1 - 1)

    def setpos(self, expr, line, col):
        return self.eval('setpos("{}", [0, {:d}, {:d}])'.format(expr, line, col))

    def select(self, a, b=None, block=False):
        add1 = lambda x: [n + 1 for n in x]
        a = add1(a)
        if b is None:
            if self.mode in VISUAL_MODES:
                self.press('<esc>')
            self.eval('cursor({:d}, {:d}, {:d})'.format(a[0], a[1], a[1]))
        else:
            b = add1(b)

            self.press('\033')
            self.setpos('.', *a)
            self.cmd('normal! v')
            # fix right hand side alignment
            if a < b:
                b = [b[0], b[1] - 1]
            self.setpos('.', *b)

    @property
    def mode(self):
        return self.eval('mode()')

if 'vim' in globals():
    new = Vim(vim.nv)
    new.notif_cb = vim.notif_cb
    new.screen = vim.screen
    vim = new
else:
    vim = Vim()
    vim._setup()
