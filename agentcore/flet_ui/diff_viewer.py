"""Side-by-side diff viewer for file changes."""

import difflib
import flet as ft


def _diff_blocks(old: str, new: str, ctx: int = 3) -> list[dict]:
    old_lines = old.splitlines() if old else []
    new_lines = new.splitlines() if new else []
    if not old_lines and not new_lines:
        return []

    sm = difflib.SequenceMatcher(None, old_lines, new_lines)
    raw = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        raw.append({
            'tag': 'change' if tag != 'equal' else 'equal',
            'os': i1, 'ol': old_lines[i1:i2],
            'ns': j1, 'nl': new_lines[j1:j2],
        })

    changes = [i for i, b in enumerate(raw) if b['tag'] == 'change']
    if not changes:
        return []

    result = []
    for i, b in enumerate(raw):
        if b['tag'] == 'change':
            result.append(b)
            continue
        lines, n = b['ol'], len(b['ol'])
        if n == 0:
            continue

        if i < changes[0]:  # before first change
            if n > ctx:
                result.append({'tag': 'fold', 'os': b['os'], 'ns': b['ns'],
                               'count': n - ctx, 'ol': lines[:-ctx], 'nl': b['nl'][:-ctx]})
            result.append({'tag': 'equal',
                           'os': b['os'] + max(0, n - ctx), 'ns': b['ns'] + max(0, n - ctx),
                           'ol': lines[-ctx:] if n > ctx else lines,
                           'nl': b['nl'][-ctx:] if n > ctx else b['nl']})
        elif i > changes[-1]:  # after last change
            keep = min(n, ctx)
            result.append({'tag': 'equal', 'os': b['os'], 'ns': b['ns'],
                           'ol': lines[:keep], 'nl': b['nl'][:keep]})
            if n > ctx:
                result.append({'tag': 'fold', 'os': b['os'] + ctx, 'ns': b['ns'] + ctx,
                               'count': n - ctx, 'ol': lines[ctx:], 'nl': b['nl'][ctx:]})
        else:  # between changes
            if n <= ctx * 2:
                result.append(b)
            else:
                result.append({'tag': 'equal', 'os': b['os'], 'ns': b['ns'],
                               'ol': lines[:ctx], 'nl': b['nl'][:ctx]})
                mid = n - ctx * 2
                result.append({'tag': 'fold', 'os': b['os'] + ctx, 'ns': b['ns'] + ctx,
                               'count': mid, 'ol': lines[ctx:ctx + mid], 'nl': b['nl'][ctx:ctx + mid]})
                result.append({'tag': 'equal',
                               'os': b['os'] + n - ctx, 'ns': b['ns'] + n - ctx,
                               'ol': lines[-ctx:], 'nl': b['nl'][-ctx:]})

    return result


class DiffViewer(ft.Container):
    """Collapsible side-by-side diff viewer."""

    _ADD_BG = "#DCFCE7"
    _DEL_BG = "#FEE2E2"
    _FOLD_BG = "#F1F5F9"
    _BORDER = "#E2E8F0"

    def __init__(self, path: str, old: str, new: str):
        super().__init__()
        self._path = path
        self._open = True
        self._blocks = _diff_blocks(old, new)
        self._folds: dict[int, dict] = {}

        added = sum(len(b['nl']) for b in self._blocks if b['tag'] == 'change')
        removed = sum(len(b['ol']) for b in self._blocks if b['tag'] == 'change')
        self._summary = f"+{added} -{removed}"

        self._arrow = ft.Icon(ft.Icons.KEYBOARD_ARROW_DOWN, size=20, color="#6366F1")
        self._panel = None

        self.expand = True
        self.content = self._expanded()
        self.border = ft.Border.all(1, self._BORDER)
        self.border_radius = 8

    # ── header ──

    def _header(self):
        fname = self._path.replace('\\', '/').rsplit('/', 1)[-1]
        return ft.Container(
            content=ft.Row([
                self._arrow,
                ft.Text(fname, size=18, weight=ft.FontWeight.W_600, color="#1E1B3A"),
                ft.Container(
                    content=ft.Text(self._summary, size=17, color="#64748B",
                                    font_family="Consolas"),
                    bgcolor="#F1F5F9", border_radius=4,
                    padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                ),
                ft.Text(self._path, size=16, color="#94A3B8",
                        overflow=ft.TextOverflow.ELLIPSIS, expand=True),
            ], spacing=6),
            padding=ft.Padding.symmetric(horizontal=10, vertical=7),
            on_click=self._toggle,
        )

    # ── row builders ──

    def _line(self, ln, lt, lbg, lcolor, rn, rt, rbg, rcolor):
        return ft.Row([
            ft.Container(content=ft.Row([
                ft.Text(str(ln) if ln else "", size=16, color="#94A3B8",
                        width=44, text_align=ft.TextAlign.RIGHT, font_family="Consolas"),
                ft.Container(width=8),
                ft.Text(lt or "", size=17, color=lcolor,
                        font_family="Consolas", expand=True),
            ], spacing=0, tight=True), bgcolor=lbg, expand=True),
            ft.VerticalDivider(width=1, color=self._BORDER),
            ft.Container(content=ft.Row([
                ft.Text(str(rn) if rn else "", size=16, color="#94A3B8",
                        width=44, text_align=ft.TextAlign.RIGHT, font_family="Consolas"),
                ft.Container(width=8),
                ft.Text(rt or "", size=17, color=rcolor,
                        font_family="Consolas", expand=True),
            ], spacing=0, tight=True), bgcolor=rbg, expand=True),
        ], spacing=0, tight=True, expand=True)

    def _fold_row(self, block):
        fid = id(block)
        self._folds[fid] = block
        c = ft.Container(
            content=ft.Row([
                ft.Text(f" {block['count']} lines unchanged", size=17,
                        color="#94A3B8", font_family="Consolas"),
                ft.Icon(ft.Icons.UNFOLD_MORE, size=18, color="#94A3B8"),
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=self._FOLD_BG,
            padding=ft.Padding.symmetric(vertical=3),
            on_click=lambda e, f=fid: self._open_fold(f),
        )
        c._fid = fid
        return c

    def _rows_for(self, block):
        tag = block['tag']
        if tag == 'fold':
            return [self._fold_row(block)]
        rows = []
        if tag == 'equal':
            for i, (ol, nl) in enumerate(zip(block['ol'], block['nl'])):
                rows.append(self._line(
                    block['os'] + i + 1, ol, "#FFFFFF", "#334155",
                    block['ns'] + i + 1, nl, "#FFFFFF", "#334155"))
        else:
            ol, nl = block['ol'], block['nl']
            for i in range(max(len(ol), len(nl))):
                ho, hn = i < len(ol), i < len(nl)
                rows.append(self._line(
                    block['os'] + i + 1 if ho else "", ol[i] if ho else "",
                    self._DEL_BG if ho else "#FFFFFF", "#991B1B" if ho else "#334155",
                    block['ns'] + i + 1 if hn else "", nl[i] if hn else "",
                    self._ADD_BG if hn else "#FFFFFF", "#166534" if hn else "#334155"))
        return rows

    # ── panels ──

    def _collapsed(self):
        return ft.Column([self._header()], spacing=0)

    def _expanded(self):
        if self._panel is None:
            self._panel = ft.Column(
                [r for b in self._blocks for r in self._rows_for(b)], spacing=0)

        expand_btn = ft.Container(
            content=ft.Row([
                ft.TextButton(
                    content=ft.Row([
                        ft.Icon(ft.Icons.UNFOLD_MORE, size=18, color="#64748B"),
                        ft.Text("Expand All", size=16, color="#64748B"),
                    ], spacing=2),
                    style=ft.ButtonStyle(
                        padding=ft.Padding.symmetric(horizontal=8, vertical=2)),
                    on_click=lambda e: self._open_all(),
                ),
            ], alignment=ft.MainAxisAlignment.END),
            padding=ft.Padding.only(right=6),
        )

        visible = sum(
            max(len(b['ol']), len(b['nl'])) if b['tag'] == 'change'
            else len(b['ol']) if b['tag'] == 'equal' else 1
            for b in self._blocks)
        h = min(visible * 26 + 40, 500)

        return ft.Column([
            self._header(), expand_btn,
            ft.Container(content=self._panel, height=h,
                         padding=ft.Padding.only(bottom=4)),
        ], spacing=0)

    # ── actions ──

    def _toggle(self, e=None):
        self._open = not self._open
        self._arrow.icon = (ft.Icons.KEYBOARD_ARROW_DOWN if self._open
                            else ft.Icons.KEYBOARD_ARROW_RIGHT)
        self.content = self._expanded() if self._open else self._collapsed()
        try:
            self.update()
        except RuntimeError:
            pass

    def _open_fold(self, fid):
        b = self._folds.get(fid)
        if not b or not self._panel:
            return
        for i, c in enumerate(self._panel.controls):
            if getattr(c, '_fid', None) == fid:
                self._panel.controls[i:i + 1] = self._rows_for({
                    'tag': 'equal', 'os': b['os'], 'ns': b['ns'],
                    'ol': b['ol'], 'nl': b['nl'],
                })
                try:
                    self._panel.update()
                except RuntimeError:
                    pass
                return

    def _open_all(self):
        if not self._panel:
            return
        new = []
        for c in list(self._panel.controls):
            fid = getattr(c, '_fid', None)
            if fid and fid in self._folds:
                b = self._folds[fid]
                new.extend(self._rows_for({
                    'tag': 'equal', 'os': b['os'], 'ns': b['ns'],
                    'ol': b['ol'], 'nl': b['nl'],
                }))
            else:
                new.append(c)
        self._panel.controls = new
        try:
            self._panel.update()
        except RuntimeError:
            pass
